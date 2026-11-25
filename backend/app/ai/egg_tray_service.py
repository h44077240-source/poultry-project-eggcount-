"""
Egg Tray Detection and Dual-View Inventory Service
Ported from Egg_Inventory_Project (egg_app.py)

Uses custom-trained YOLO weights (best.pt / egg_detector.pt) to count egg trays
using dual perspective photos (Top View for stacks, Side View for layer pitch).
"""

import os
import cv2
import numpy as np
import base64
import logging
from typing import Optional, Dict, Any, List
from ultralytics import YOLO

logger = logging.getLogger("egg_tray_service")

EGGS_PER_TRAY = 30
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "egg_detector.pt")

_egg_tray_model: Optional[YOLO] = None


def get_egg_tray_model() -> Optional[YOLO]:
    """Loads and caches the dedicated egg tray YOLO model."""
    global _egg_tray_model
    if _egg_tray_model is None:
        candidate_paths = [
            MODEL_PATH,
            os.path.join(os.path.dirname(__file__), "models", "egg_tray_best.pt"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "models", "egg_detector.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "app", "ai", "models", "egg_detector.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "scratch", "Egg_Inventory_Project", "best.pt")),
        ]
        chosen = next((p for p in candidate_paths if os.path.exists(p)), None)
        if chosen:
            try:
                logger.info(f"Loading Egg Tray YOLO model from {chosen}")
                _egg_tray_model = YOLO(chosen)
            except Exception as e:
                logger.error(f"Failed to load egg tray model: {e}", exc_info=True)
                _egg_tray_model = None
    return _egg_tray_model


def enhance_image(img: np.ndarray) -> np.ndarray:
    """Brightens dark shadows near the floor while preserving highlights using CLAHE."""
    if img is None:
        raise ValueError("Image array is None")
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def count_column_trays(col_boxes: np.ndarray) -> int:
    """Filters out both overlapping boxes and skipped double-gaps, then uses mean pitch."""
    if len(col_boxes) <= 1:
        return len(col_boxes)

    # 1. Standardize box centers from flat bottom edge minus half a normal tray height
    box_heights = col_boxes[:, 3] - col_boxes[:, 1]
    normal_height = np.median(box_heights)
    adj_y_centers = np.sort(col_boxes[:, 3] - (normal_height / 2))

    # 2. Remove overlapping duplicate boxes on the same tray
    gaps = np.diff(adj_y_centers)
    valid_gaps = gaps[gaps > (normal_height * 0.45)]

    if len(valid_gaps) == 0:
        return 1

    # 3. Remove wide double-gaps (caused by skipped middle trays) before taking the mean
    med_gap = np.median(valid_gaps)
    single_tray_gaps = valid_gaps[valid_gaps < (med_gap * 1.5)]
    if len(single_tray_gaps) == 0:
        single_tray_gaps = valid_gaps

    # 4. Mean of true single-tray gaps handles perspective shrinkage without under/overcounting
    tray_pitch = float(np.mean(single_tray_gaps))
    total_span = float(adj_y_centers[-1] - adj_y_centers[0])

    if tray_pitch <= 0:
        return len(col_boxes)

    return int(round(total_span / tray_pitch)) + 1


def group_columns(side_boxes: np.ndarray) -> List[np.ndarray]:
    """Automatically groups side detections into 1, 2, or more vertical stacks."""
    if len(side_boxes) == 0:
        return []
    x_centers = (side_boxes[:, 0] + side_boxes[:, 2]) / 2
    avg_box_width = np.median(side_boxes[:, 2] - side_boxes[:, 0])
    sorted_indices = np.argsort(x_centers)

    columns = []
    current_col = [side_boxes[sorted_indices[0]]]
    for idx in sorted_indices[1:]:
        box = side_boxes[idx]
        box_x = (box[0] + box[2]) / 2
        prev_x = np.mean([(b[0] + b[2]) / 2 for b in current_col])

        if abs(box_x - prev_x) < (avg_box_width * 0.5):
            current_col.append(box)
        else:
            columns.append(np.array(current_col))
            current_col = [box]
    columns.append(np.array(current_col))
    return columns


def analyze_dual_egg_trays(top_image_bytes: bytes, side_image_bytes: bytes) -> Dict[str, Any]:
    """
    Performs full dual-view egg inventory analysis:
    1. Enhances both images using adaptive CLAHE.
    2. Runs YOLO on Top View (conf=0.55, iou=0.20) to detect number of stacks.
    3. Runs YOLO on Side View (conf=0.30, iou=0.45) to detect vertical layers per column.
    4. Computes total trays = num_stacks * stack_height and total eggs = total_trays * 30.
    5. Returns annotated visualizations (base64) with bounding boxes for both views.
    """
    model = get_egg_tray_model()
    if model is None:
        raise RuntimeError("Egg tray YOLO model could not be loaded from disk.")

    top_np = np.frombuffer(top_image_bytes, np.uint8)
    top_img_raw = cv2.imdecode(top_np, cv2.IMREAD_COLOR)
    side_np = np.frombuffer(side_image_bytes, np.uint8)
    side_img_raw = cv2.imdecode(side_np, cv2.IMREAD_COLOR)

    if top_img_raw is None or side_img_raw is None:
        raise ValueError("Could not decode top or side image bytes into valid OpenCV image.")

    top_img = enhance_image(top_img_raw)
    side_img = enhance_image(side_img_raw)

    top_res = model(top_img, conf=0.55, iou=0.20, verbose=False)[0]
    side_res = model(side_img, conf=0.30, iou=0.45, verbose=False)[0]

    num_stacks = len(top_res.boxes)
    if len(side_res.boxes) > 0:
        side_boxes = side_res.boxes.xyxy.cpu().numpy()
        columns = group_columns(side_boxes)
        col_heights = [count_column_trays(col) for col in columns]
        stack_height = max(col_heights) if col_heights else 0
    else:
        col_heights = []
        stack_height = 0

    if num_stacks == 0 and stack_height > 0:
        num_stacks = 1
    elif num_stacks > 0 and stack_height == 0:
        stack_height = 1

    total_trays = num_stacks * stack_height
    total_eggs = total_trays * EGGS_PER_TRAY

    # Generate annotated images with bounding boxes plotted
    top_plotted = top_res.plot()
    side_plotted = side_res.plot()

    _, top_buf = cv2.imencode(".jpg", top_plotted)
    top_b64 = "data:image/jpeg;base64," + base64.b64encode(top_buf).decode("utf-8")

    _, side_buf = cv2.imencode(".jpg", side_plotted)
    side_b64 = "data:image/jpeg;base64," + base64.b64encode(side_buf).decode("utf-8")

    height_info = f"column heights {col_heights}" if col_heights else "single stack"
    notes = (
        f"Dual View Tray Analysis: Top view identified {num_stacks} stack(s). "
        f"Side view measured {stack_height} layer(s) per stack ({height_info}). "
        f"Calculation: {num_stacks} stack(s) × {stack_height} layer(s) = {total_trays} trays ({total_eggs} eggs)."
    )

    return {
        "success": True,
        "egg_count": total_eggs,
        "tray_count": total_trays,
        "expected_egg_count": total_eggs,
        "missing_egg_count": 0,
        "hen_count": 0,
        "num_stacks": num_stacks,
        "stack_height": stack_height,
        "col_heights": col_heights,
        "tray_types": {
            "green_plastic": total_trays,
            "paper_cardboard": 0,
            "other": 0,
            "unknown": 0
        },
        "confidence": "high" if total_trays > 0 else "medium",
        "image_quality": "good",
        "notes": notes,
        "top_annotated_image": top_b64,
        "side_annotated_image": side_b64,
        "annotated_image": side_b64,
    }
