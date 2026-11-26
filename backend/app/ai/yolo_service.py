import os
import cv2
import numpy as np
import base64
# pyrefly: ignore [missing-import]
from ultralytics import YOLO

# Global model instances
model = None
egg_model = None
tray_model = None

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "egg_detector.pt")
ALT_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../models/best.pt"))
FALLBACK_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../yolov8s-world.pt"))

def load_model():
    global model, egg_model, tray_model
    if model is None or egg_model is None:
        try:
            if model is None:
                from app.ai.shared_model import get_shared_model
                model = get_shared_model()

            if egg_model is None:
                egg_candidate_paths = [
                    MODEL_PATH,
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "models", "egg_detector.pt")),
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../egg_detector.pt")),
                    os.path.abspath(os.path.join(os.getcwd(), "backend", "egg_detector.pt")),
                    os.path.abspath(os.path.join(os.getcwd(), "egg_detector.pt")),
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../egg-detection-system/backend/models/egg_detector.pt")),
                ]
                egg_chosen = next((p for p in egg_candidate_paths if os.path.exists(p)), None)
                if egg_chosen:
                    try:
                        print(f"[AI] Loading dedicated egg detector from {egg_chosen}")
                        egg_model = YOLO(egg_chosen)
                    except Exception as egg_err:
                        print(f"[AI] Notice: Could not load egg detector: {egg_err}")
                        egg_model = None

            # YOLOWorld fallback is disabled by default to prevent allocating >1GB of CLIP transformer RAM
            if os.environ.get("ENABLE_YOLO_WORLD", "false").lower() == "true":
                try:
                    from ultralytics import YOLOWorld
                    print("[AI] Loading YOLO-World for trays and hens.")
                    tray_model_path = FALLBACK_MODEL_PATH if os.path.exists(FALLBACK_MODEL_PATH) else "yolov8s-worldv2.pt"
                    if os.path.exists(tray_model_path):
                        tray_model = YOLOWorld(tray_model_path)
                        tray_model.set_classes(["egg tray", "hen"])
                except Exception as e:
                    print(f"[AI] YOLOWorld load notice: {e}")
                    tray_model = None

        except Exception as e:
            print(f"[AI] Error loading model: {e}")
            raise e

    return model, tray_model

def detect_objects_image(image: np.ndarray, conf_threshold: float = 0.35, iou_threshold: float = 0.45) -> dict:
    """
    Runs YOLO inference on a raw OpenCV image array and returns detection results.
    """
    model_instance, tray_model_instance = load_model()
    if not model_instance and not egg_model:
        raise ValueError("Failed to load YOLO model.")

    if image is None:
        raise ValueError("Image array is None.")

    # Run inference for main model with optimal resolution on CPU/Render
    import torch
    target_imgsz = 416 if os.environ.get("RENDER") == "true" or not torch.cuda.is_available() else 640
    results = []
    if model_instance is not None:
        try:
            results = model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=target_imgsz)
        except Exception as e:
            print(f"[AI] Main model error: {e}")
            results = []
    
    # Run inference for egg/trays using dedicated egg tray model
    egg_results = None
    if egg_model is not None:
        try:
            # Use threshold provided, but adapt for egg tray detection down to 0.20 if default is higher
            eff_conf = min(conf_threshold, 0.20) if conf_threshold > 0.20 else conf_threshold
            egg_results = egg_model(image, conf=eff_conf, iou=iou_threshold, imgsz=target_imgsz)
        except Exception as e:
            print(f"[AI] Dedicated egg detector error: {e}")
            egg_results = None

    # Run inference for trays if needed
    tray_results = None
    if tray_model_instance:
        try:
            tray_results = tray_model_instance(image, conf=conf_threshold, iou=iou_threshold, imgsz=640)
        except Exception:
            tray_results = None
        
    detections = []
    annotated_image = image.copy()
    
    egg_count = 0
    tray_count = 0
    hen_count = 0
    egg_conf_sum = 0
    tray_conf_sum = 0
    
    def process_boxes(boxes, class_names, is_tray_only=False, is_egg_only=False):
        nonlocal egg_count, tray_count, hen_count, egg_conf_sum, tray_conf_sum, detections, annotated_image
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())
            
            raw_class_name = class_names.get(cls_id, "unknown").lower()
            if is_tray_only or "tray" in raw_class_name:
                class_name = "egg_tray"
            elif is_egg_only or "egg" in raw_class_name:
                class_name = "egg"
            elif any(k in raw_class_name for k in ("hen", "comb", "bird", "chicken")):
                class_name = "hen"
            else:
                continue  # Skip everything else

            x = int(x1)
            y = int(y1)
            width = int(x2 - x1)
            height = int(y2 - y1)
            
            if class_name == "egg_tray":
                tray_count += 1
                color = (255, 140, 0) # Clear Cyan/Blue in BGR
                label = f"EGG TRAY {tray_count} ({int(conf*100)}%)"
                tray_conf_sum += conf
                det_id = tray_count
            elif class_name == "hen":
                hen_count += 1
                color = (0, 0, 255) # Red in BGR
                label = f"HEN/COMB {hen_count} ({int(conf*100)}%)"
                det_id = hen_count
            elif class_name == "egg":
                egg_count += 1
                color = (0, 255, 255) # Yellow in BGR
                label = f"EGG {egg_count} ({int(conf*100)}%)"
                egg_conf_sum += conf
                det_id = egg_count
            else:
                continue
            
            detections.append({
                "id": det_id,
                "class": class_name,
                "confidence": round(conf, 3),
                "bbox": [x, y, x + width, y + height]
            })
            
            thickness = max(2, int(image.shape[0] * 0.003))
            cv2.rectangle(annotated_image, (x, y), (x + width, y + height), color, thickness)
            
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.5, image.shape[0] * 0.0006)
            font_thickness = max(1, int(image.shape[0] * 0.0015))
            text_size = cv2.getTextSize(label, font, font_scale, font_thickness)[0]
            cv2.rectangle(annotated_image, (x, max(0, y - text_size[1] - 8)), (x + text_size[0] + 6, max(text_size[1] + 8, y)), color, -1)
            cv2.putText(annotated_image, label, (x + 3, max(text_size[1] + 2, y - 5)), font, font_scale, (255, 255, 255), font_thickness)

    # Process main model results (Hen Comb)
    for result in results:
        class_names = getattr(result, "names", {0: "HEN_COMB"})
        process_boxes(result.boxes, class_names)

    # Process dedicated egg/tray model results with intelligent geometry & clutter rejection
    if egg_results:
        for result in egg_results:
            if len(result.boxes) > 0:
                raw_boxes = result.boxes.xyxy.cpu().numpy()
                raw_confs = result.boxes.conf.cpu().numpy()
                widths = raw_boxes[:, 2] - raw_boxes[:, 0]
                heights = raw_boxes[:, 3] - raw_boxes[:, 1]
                ar = widths / np.maximum(heights, 1)
                median_ar = float(np.median(ar)) if len(ar) > 0 else 1.0

                if median_ar > 1.8:
                    # Side view perspective: eliminate ground cracks, sky, and isolated clutter
                    try:
                        from app.ai.egg_tray_service import filter_and_validate_side_boxes
                        valid_cols = filter_and_validate_side_boxes(raw_boxes, raw_confs, image.shape)
                        for col_b, col_c in valid_cols:
                            for b, c in zip(col_b, col_c):
                                x1, y1, x2, y2 = b
                                tray_count += 1
                                det_id = tray_count
                                conf = float(c)
                                tray_conf_sum += conf
                                detections.append({
                                    "id": det_id,
                                    "class": "egg_tray",
                                    "confidence": round(conf, 3),
                                    "bbox": [int(x1), int(y1), int(x2), int(y2)]
                                })
                                cv2.rectangle(annotated_image, (int(x1), int(y1)), (int(x2), int(y2)), (255, 140, 0), 2)
                                label = f"EGG TRAY {tray_count} ({int(conf*100)}%)"
                                (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                                cv2.rectangle(annotated_image, (int(x1), max(0, int(y1) - lh - 4)), (int(x1) + lw + 4, int(y1)), (255, 140, 0), -1)
                                cv2.putText(annotated_image, label, (int(x1) + 2, max(lh + 1, int(y1) - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                    except Exception:
                        class_names = getattr(result, "names", {0: "egg_tray"})
                        process_boxes(result.boxes, class_names)
                else:
                    # Top view perspective: eliminate mesh clutter and split seams
                    try:
                        from app.ai.egg_tray_service import filter_top_view_trays
                        filt_b, filt_c = filter_top_view_trays(raw_boxes, raw_confs)
                        for b, c in zip(filt_b, filt_c):
                            x1, y1, x2, y2 = b
                            tray_count += 1
                            det_id = tray_count
                            conf = float(c)
                            tray_conf_sum += conf
                            detections.append({
                                "id": det_id,
                                "class": "egg_tray",
                                "confidence": round(conf, 3),
                                "bbox": [int(x1), int(y1), int(x2), int(y2)]
                            })
                            cv2.rectangle(annotated_image, (int(x1), int(y1)), (int(x2), int(y2)), (255, 140, 0), 2)
                            label = f"EGG TRAY {tray_count} ({int(conf*100)}%)"
                            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                            cv2.rectangle(annotated_image, (int(x1), max(0, int(y1) - lh - 4)), (int(x1) + lw + 4, int(y1)), (255, 140, 0), -1)
                            cv2.putText(annotated_image, label, (int(x1) + 2, max(lh + 1, int(y1) - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                    except Exception:
                        class_names = getattr(result, "names", {0: "egg_tray"})
                        process_boxes(result.boxes, class_names)
        
    # Process tray model results if present
    if tray_results:
        for result in tray_results:
            class_names = getattr(result, "names", {0: "egg tray", 1: "hen"})
            process_boxes(result.boxes, class_names, is_tray_only=True)

    _, buffer = cv2.imencode('.jpg', annotated_image)
    encoded_img = base64.b64encode(buffer).decode('utf-8')
    
    avg_tray_conf = (tray_conf_sum / max(1, tray_count)) if tray_count > 0 else 0.0
    avg_egg_conf = (egg_conf_sum / max(1, egg_count)) if egg_count > 0 else 0.0
    
    final_conf = avg_tray_conf if tray_count > 0 else avg_egg_conf
    expected_eggs = tray_count * 30
    final_egg_count = egg_count if (egg_count > 0 and egg_count != expected_eggs) else expected_eggs
    missing_eggs = max(0, expected_eggs - egg_count) if (egg_count > 0 and expected_eggs > egg_count) else 0
    
    return {
        "success": True,
        "tray_count": tray_count,
        "hen_count": hen_count,
        "egg_count": final_egg_count,
        "expected_egg_count": expected_eggs,
        "missing_egg_count": missing_eggs,
        "confidence": round(final_conf, 3),
        "detections": detections,
        "result_image": encoded_img
    }

def detect_objects(image_bytes: bytes, conf_threshold: float = 0.35, iou_threshold: float = 0.45) -> dict:
    """
    Runs YOLO inference on the image bytes and returns detection results for eggs and trays,
    and a base64 annotated image.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes.")
        
    return detect_objects_image(image, conf_threshold, iou_threshold)
