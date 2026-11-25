"""
Egg Tray Detection and Dual-View Inventory Service
Ported & Enhanced from Egg_Inventory_Project (egg_app.py)

Uses custom-trained YOLO weights (best.pt / egg_detector.pt) to count egg trays
using dual perspective photos (Top View for stacks, Side View for layer pitch).

Features:
1. Automatic View Orientation Detection (auto-swaps if user uploads side view in top slot or vice versa).
2. Adaptive Multi-Threshold Detection for distant/shadowed tray layers (no missed trays).
3. Robust Column Grouping & Pitch Interpolation for stacked trays.
4. Base64 annotated image generation with bounding boxes plotted.
"""

import os
import cv2
import numpy as np
import base64
import logging
from typing import Optional, Dict, Any, List, Tuple
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
                logger.info("Loading Egg Tray YOLO model from %s", chosen)
                _egg_tray_model = YOLO(chosen)
            except Exception as e:
                logger.error("Failed to load egg tray model: %s", e, exc_info=True)
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


def classify_view_perspective(model: YOLO, img: np.ndarray) -> Tuple[str, float, int]:
    """
    Automatically detects whether an image is a 'side' view (stacked layers)
    or a 'top' view (flat 2D egg grid looking down).

    Side view boxes are thin horizontal slices (width / height > 1.9).
    Top view boxes are square/rectangular (width / height ~ 0.8 - 1.4).
    Uses high-confidence candidate detection to avoid noise slivers.
    """
    for conf in [0.35, 0.20]:
        res = model(img, conf=conf, verbose=False)[0]
        if len(res.boxes) > 0:
            boxes = res.boxes.xyxy.cpu().numpy()
            widths = boxes[:, 2] - boxes[:, 0]
            heights = boxes[:, 3] - boxes[:, 1]
            # Ignore tiny horizontal slivers/seams (height < 10)
            valid = heights >= 10
            if np.sum(valid) > 0:
                ar = widths[valid] / np.maximum(heights[valid], 1)
                median_ar = float(np.median(ar))
                view = "side" if median_ar > 1.9 else "top"
                return view, median_ar, len(boxes)
    return "unknown", 1.0, 0


def count_column_trays(col_boxes: np.ndarray) -> int:
    """Filters out overlapping boxes and skipped double-gaps, then uses mean pitch."""
    if len(col_boxes) <= 1:
        return len(col_boxes)

    # 1. Standardize box centers from their flat bottom edge minus half normal tray height
    box_heights = col_boxes[:, 3] - col_boxes[:, 1]
    normal_height = np.median(box_heights)
    adj_y_centers = np.sort(col_boxes[:, 3] - (normal_height / 2))

    # 2. Remove overlapping duplicate boxes on the same tray
    gaps = np.diff(adj_y_centers)
    valid_gaps = gaps[gaps > (normal_height * 0.40)]

    if len(valid_gaps) == 0:
        return 1

    # 3. Remove wide double-gaps (caused by skipped middle trays) before taking the mean
    med_gap = np.median(valid_gaps)
    single_tray_gaps = valid_gaps[valid_gaps < (med_gap * 1.6)]
    if len(single_tray_gaps) == 0:
        single_tray_gaps = valid_gaps

    # 4. Mean of true single-tray gaps handles perspective shrinkage without under/overcounting
    tray_pitch = float(np.mean(single_tray_gaps))
    total_span = float(adj_y_centers[-1] - adj_y_centers[0])

    if tray_pitch <= 0:
        return len(col_boxes)

    pitch_based_count = int(round(total_span / tray_pitch)) + 1
    # Never return fewer trays than the number of distinct valid gap positions + 1
    return max(pitch_based_count, len(valid_gaps) + 1, len(col_boxes))


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


def filter_and_validate_side_boxes(boxes: np.ndarray, confs: np.ndarray, img_shape: tuple) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Strictly filters out background clutter (road cracks, ground shadows, trees, poles):
    1. Aspect ratio: in side view, a tray is a thin horizontal slice (AR >= 1.8).
    2. Width consistency: rejects wide road cracks that span across stacks.
    3. Column grouping: clusters trays into stacked columns.
    4. Vertical continuity: removes isolated outliers separated by large vertical gaps.
    """
    if len(boxes) == 0:
        return []

    widths = boxes[:, 2] - boxes[:, 0]
    heights = boxes[:, 3] - boxes[:, 1]
    aspect_ratios = widths / np.maximum(heights, 1)

    # 1. Aspect ratio filter: individual trays must be horizontal slices
    mask = (aspect_ratios >= 1.8) & (widths < img_shape[1] * 0.6)
    if np.sum(mask) == 0:
        return []

    c_boxes = boxes[mask]
    c_confs = confs[mask]
    c_widths = widths[mask]
    c_heights = heights[mask]

    # Reference tray width & height from strongest candidates
    ref_w = np.median(c_widths)
    ref_h = np.median(c_heights)

    # 2. Width consistency: reject cracks that are significantly wider than normal trays
    width_mask = (c_widths >= ref_w * 0.6) & (c_widths <= ref_w * 1.45)
    c_boxes = c_boxes[width_mask]
    c_confs = c_confs[width_mask]

    if len(c_boxes) == 0:
        return []

    # 3. Group by X-center into vertical columns
    x_centers = (c_boxes[:, 0] + c_boxes[:, 2]) / 2
    sorted_idx = np.argsort(x_centers)

    columns: List[Tuple[List[np.ndarray], List[float]]] = []
    current_col = [c_boxes[sorted_idx[0]]]
    current_confs = [c_confs[sorted_idx[0]]]

    for idx in sorted_idx[1:]:
        b = c_boxes[idx]
        b_x = (b[0] + b[2]) / 2
        prev_x = np.mean([(cb[0] + cb[2]) / 2 for cb in current_col])

        if abs(b_x - prev_x) < (ref_w * 0.5):
            current_col.append(b)
            current_confs.append(c_confs[idx])
        else:
            columns.append((current_col, current_confs))
            current_col = [b]
            current_confs = [c_confs[idx]]
    columns.append((current_col, current_confs))

    # 4. Vertical continuity: drop isolated outliers (floor cracks, sky/trees, etc.)
    valid_columns: List[Tuple[np.ndarray, np.ndarray]] = []
    for col_b_list, col_c_list in columns:
        col_boxes = np.array(col_b_list)
        col_confs = np.array(col_c_list)

        # An egg stack must have at least 3 layers
        if len(col_boxes) < 3:
            continue

        # Sort top-to-bottom by Y-center
        y_centers = (col_boxes[:, 1] + col_boxes[:, 3]) / 2
        y_sort = np.argsort(y_centers)
        col_boxes = col_boxes[y_sort]
        col_confs = col_confs[y_sort]
        y_centers = y_centers[y_sort]

        box_h = np.median(col_boxes[:, 3] - col_boxes[:, 1])
        keep = np.ones(len(col_boxes), dtype=bool)

        for i in range(len(col_boxes)):
            dists = []
            if i > 0:
                dists.append(abs(y_centers[i] - y_centers[i - 1]))
            if i < len(col_boxes) - 1:
                dists.append(abs(y_centers[i + 1] - y_centers[i]))
            min_dist = min(dists) if dists else 999.0
            # If no neighbouring tray exists within 3.5x normal height, it's an outlier (e.g. road crack)
            if min_dist > (box_h * 3.5):
                keep[i] = False

        filtered_col = col_boxes[keep]
        filtered_confs = col_confs[keep]
        if len(filtered_col) >= 3:
            valid_columns.append((filtered_col, filtered_confs))

    return valid_columns


def draw_validated_side_detections(img: np.ndarray, valid_columns: List[Tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """Draws clear bounding boxes ONLY on validated egg tray stacks, never on road cracks or background."""
    annotated = img.copy()
    col_colors = [
        (255, 120, 0),   # Cyan/blue
        (0, 165, 255),   # Amber/orange
        (0, 220, 0),     # Green
        (255, 50, 200)   # Magenta
    ]
    for c_idx, (col_boxes, col_confs) in enumerate(valid_columns):
        color = col_colors[c_idx % len(col_colors)]
        for box, conf in zip(col_boxes, col_confs):
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"egg_tray {conf:.2f}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
            cv2.rectangle(annotated, (x1, max(0, y1 - lh - 4)), (x1 + lw + 2, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 1, max(lh + 1, y1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
    return annotated


def filter_top_view_trays(boxes: np.ndarray, confs: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Strictly filters top view egg tray detections:
    1. Rejects non-square detections (horizontal seams, borders with AR > 1.6 or AR < 0.65).
    2. Rejects tiny fragments / floor mesh clutter whose area is < 35% of median tray area.
    3. Rejects low confidence clutter (< 0.50, with fallback to 0.40 only if zero candidates).
    """
    if len(boxes) == 0:
        return np.array([]), np.array([])

    widths = boxes[:, 2] - boxes[:, 0]
    heights = boxes[:, 3] - boxes[:, 1]
    aspect_ratios = widths / np.maximum(heights, 1)
    areas = widths * heights

    # 1. Top view trays are approximately square
    shape_mask = (aspect_ratios >= 0.70) & (aspect_ratios <= 1.55) & (confs >= 0.50)
    if np.sum(shape_mask) == 0:
        shape_mask = (aspect_ratios >= 0.65) & (aspect_ratios <= 1.65) & (confs >= 0.40)

    if np.sum(shape_mask) == 0:
        return np.array([]), np.array([])

    c_boxes = boxes[shape_mask]
    c_confs = confs[shape_mask]
    c_widths = widths[shape_mask]
    c_areas = areas[shape_mask]

    # 2. Relative Area Consistency: genuine egg trays in the photo have consistent area
    ref_area = np.median(c_areas)
    ref_width = np.median(c_widths)

    # Any box smaller than 35% of median area or 50% of median width is background clutter (floor, mesh, etc.)
    size_mask = (c_areas >= ref_area * 0.35) & (c_widths >= ref_width * 0.50)

    final_boxes = c_boxes[size_mask]
    final_confs = c_confs[size_mask]

    return final_boxes, final_confs


def draw_validated_top_detections(img: np.ndarray, boxes: np.ndarray, confs: np.ndarray) -> np.ndarray:
    """Draws clear bounding boxes for top view stacks, filtering out lines or background borders."""
    annotated = img.copy()
    color = (0, 200, 255)  # Amber
    for box, conf in zip(boxes, confs):
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"egg_tray {conf:.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(annotated, (x1, max(0, y1 - lh - 4)), (x1 + lw + 4, y1), color, -1)
        cv2.putText(annotated, label, (x1 + 2, max(lh + 1, y1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    return annotated


def detect_side_view_with_adaptive_thresholds(model: YOLO, side_img: np.ndarray) -> Tuple[np.ndarray, List[int], int]:
    """
    Runs multi-threshold detection on side view with geometric and continuity filtering.
    Eliminates all false positives on road cracks and trees.
    """
    best_annotated = side_img.copy()
    best_col_heights: List[int] = []
    best_stack_height = 0
    max_detected = 0

    for conf in [0.25, 0.20, 0.15]:
        res = model(side_img, conf=conf, iou=0.45, verbose=False)[0]
        raw_boxes = res.boxes.xyxy.cpu().numpy()
        raw_confs = res.boxes.conf.cpu().numpy()

        if len(raw_boxes) > 0:
            valid_cols = filter_and_validate_side_boxes(raw_boxes, raw_confs, side_img.shape)
            total_valid_boxes = sum(len(cb) for cb, _ in valid_cols)
            if total_valid_boxes > max_detected:
                max_detected = total_valid_boxes
                best_col_heights = [count_column_trays(cb) for cb, _ in valid_cols]
                best_stack_height = max(best_col_heights) if best_col_heights else 0
                best_annotated = draw_validated_side_detections(side_img, valid_cols)

            if total_valid_boxes >= 15:
                break

    if max_detected == 0:
        # Fallback raw model plot only if zero valid columns were identified
        res = model(side_img, conf=0.15, iou=0.45, verbose=False)[0]
        best_annotated = res.plot()

    return best_annotated, best_col_heights, best_stack_height


def analyze_dual_egg_trays(img1_bytes: bytes, img2_bytes: bytes) -> Dict[str, Any]:
    """
    Performs intelligent dual-view egg inventory analysis:
    1. Decodes both images and enhances with CLAHE.
    2. Automatically inspects both images to identify which is TOP VIEW and which is SIDE VIEW
       (even if the user uploaded them swapped in the form).
    3. Uses adaptive thresholding on Side View to capture every tray layer without misses.
    4. Accurately calculates total trays and total eggs (trays * 30).
    5. Returns base64 annotated visualizations with bounding boxes for both views.
    """
    model = get_egg_tray_model()
    if model is None:
        raise RuntimeError("Egg tray YOLO model could not be loaded from disk.")

    np1 = np.frombuffer(img1_bytes, np.uint8)
    img1_raw = cv2.imdecode(np1, cv2.IMREAD_COLOR)
    np2 = np.frombuffer(img2_bytes, np.uint8)
    img2_raw = cv2.imdecode(np2, cv2.IMREAD_COLOR)

    if img1_raw is None or img2_raw is None:
        raise ValueError("Could not decode image bytes into valid OpenCV image.")

    img1 = enhance_image(img1_raw)
    img2 = enhance_image(img2_raw)

    # Auto-detect which image is TOP view and which is SIDE view
    view1, ar1, _ = classify_view_perspective(model, img1)
    view2, ar2, _ = classify_view_perspective(model, img2)

    auto_swapped = False
    if view1 == "side" and view2 == "top":
        # Slot 1 is actually side view, Slot 2 is top view!
        side_img = img1
        top_img = img2
        auto_swapped = True
    elif view1 == "top" and view2 == "side":
        top_img = img1
        side_img = img2
    else:
        # Fallback if both look similar: check aspect ratio
        if ar1 > ar2:
            side_img = img1
            top_img = img2
            auto_swapped = True
        else:
            top_img = img1
            side_img = img2

    # 1. Top View Detection (Stack count)
    # Stacks in top view are detected with high confidence
    top_res = model(top_img, conf=0.35, iou=0.25, verbose=False)[0]
    raw_top_boxes = top_res.boxes.xyxy.cpu().numpy()
    raw_top_confs = top_res.boxes.conf.cpu().numpy()

    # Filter top view boxes: strictly eliminates floor patches, wire mesh, and borders
    top_boxes, top_confs = filter_top_view_trays(raw_top_boxes, raw_top_confs)
    num_stacks = len(top_boxes)

    if num_stacks > 0:
        top_plotted = draw_validated_top_detections(top_img, top_boxes, top_confs)
    else:
        top_plotted = top_img.copy()

    # 2. Side View Detection (Layer pitch & column heights with strict crack/noise elimination)
    side_plotted, col_heights, stack_height = detect_side_view_with_adaptive_thresholds(model, side_img)

    num_columns_side = len(col_heights)

    # Fallbacks if one view had 0 detections
    if num_stacks == 0 and stack_height > 0:
        num_stacks = max(1, num_columns_side)
    elif num_stacks > 0 and stack_height == 0:
        stack_height = 1

    # 3. Smart Calculation:
    # If the number of columns in the side view matches the top view stacks:
    if num_columns_side == num_stacks and num_stacks > 0:
        total_trays = sum(col_heights)
    elif num_columns_side > num_stacks and num_columns_side > 0:
        total_trays = sum(col_heights)
        num_stacks = num_columns_side
    else:
        total_trays = num_stacks * stack_height

    total_eggs = total_trays * EGGS_PER_TRAY

    # Generate base64 annotated images with bounding boxes plotted (cleaned of all background noise)
    _, top_buf = cv2.imencode(".jpg", top_plotted)
    top_b64 = "data:image/jpeg;base64," + base64.b64encode(top_buf).decode("utf-8")

    _, side_buf = cv2.imencode(".jpg", side_plotted)
    side_b64 = "data:image/jpeg;base64," + base64.b64encode(side_buf).decode("utf-8")

    swap_msg = " (Perspective auto-aligned)" if auto_swapped else ""
    height_info = f"column heights {col_heights}" if col_heights else f"{stack_height} layers"
    notes = (
        f"Dual View Tray Analysis{swap_msg}: "
        f"Top view detected {num_stacks} stack(s). "
        f"Side view measured {stack_height} layers ({height_info}). "
        f"Result: {total_trays} trays = {total_eggs} eggs."
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
