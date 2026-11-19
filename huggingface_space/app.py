import gradio as gr
from ultralytics import YOLO
import cv2
import numpy as np
import os
import math

# 1. Load trained Hen Comb YOLO model
MODEL_PATH = "best.pt"
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model file '{MODEL_PATH}' not found in current directory.")

model = YOLO(MODEL_PATH)


def draw_custom_hen_boxes(frame_bgr, boxes_xyxy, scores=None, start_id=1, total_count=None):
    """
    Renders the exact GioTag Neon Green Studio Bounding Boxes with HEAD tags,
    white corner accents, center target reticles, and Telemetry HUD (matching localhost).
    """
    display = frame_bgr.copy()
    h, w = display.shape[:2]
    count = len(boxes_xyxy)
    
    for idx, box in enumerate(boxes_xyxy):
        hid = start_id + idx
        x1, y1, x2, y2 = map(int, box[:4])
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(0, min(w - 1, x2))
        y2 = max(0, min(h - 1, y2))
        
        bw, bh = x2 - x1, y2 - y1
        if bw < 4 or bh < 4:
            continue
            
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        
        # 1. Glowing Neon Green box outline (exact BGR: 0, 255, 0)
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # 2. White corner brackets
        c_len = max(5, int(min(bw, bh) * 0.28))
        for px, py, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
            cv2.line(display, (px, py), (px + dx * c_len, py), (255, 255, 255), 2, cv2.LINE_AA)
            cv2.line(display, (px, py), (px, py + dy * c_len), (255, 255, 255), 2, cv2.LINE_AA)
            
        # 3. Center target reticle dot placed directly on the comb
        cv2.circle(display, (cx, cy), 3, (0, 255, 0), -1)
        cv2.circle(display, (cx, cy), 1, (255, 255, 255), -1)
        
        # 4. Solid green badge HEAD #{hid} with black text
        conf_str = f" {scores[idx]:.2f}" if scores is not None and idx < len(scores) else ""
        lbl_text = f"HEAD #{hid}{conf_str}"
        (tw, th), _ = cv2.getTextSize(lbl_text, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
        badge_y1 = max(0, y1 - th - 6)
        badge_y2 = y1
        badge_x1 = x1
        badge_x2 = min(w - 1, x1 + tw + 8)
        cv2.rectangle(display, (badge_x1, badge_y1), (badge_x2, badge_y2), (0, 255, 0), -1)
        cv2.putText(display, lbl_text, (badge_x1 + 4, badge_y2 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1, cv2.LINE_AA)
        
    # 5. Top-Left Telemetry HUD Card
    hud_w = 210
    hud_h = 75
    cv2.rectangle(display, (8, 12), (8 + hud_w, 12 + hud_h), (0, 0, 0), -1)
    cv2.rectangle(display, (8, 12), (8 + hud_w, 12 + hud_h), (0, 255, 0), 1)
    
    cv2.putText(display, "AI MODEL: YOLOv8 HEN_COMB", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(display, f"HEN HEADS: {count}", (14, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 0), 2, cv2.LINE_AA)
    
    tot = total_count if total_count is not None else count
    cv2.putText(display, f"TOTAL COUNTED: {tot}", (14, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 215, 255), 2, cv2.LINE_AA)
    
    return display


def detect_image(image, conf_threshold):
    """Detect hen combs in an image with custom Neon Green boxes."""
    if image is None:
        return None, "No image provided"
        
    # Convert RGB from Gradio to BGR for OpenCV
    if len(image.shape) == 3 and image.shape[2] == 3:
        frame_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = image.copy()
        
    results = model.predict(source=frame_bgr, conf=conf_threshold, verbose=False)
    res = results[0]
    
    boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None else []
    scores = res.boxes.conf.cpu().numpy() if res.boxes is not None else []
    
    annotated_bgr = draw_custom_hen_boxes(frame_bgr, boxes, scores=scores)
    annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
    
    count = len(boxes)
    status_text = f"✅ Detected {count} Hen Comb(s) | Neon Green Box Styling (Confidence >= {conf_threshold:.2f})"
    return annotated_rgb, status_text


def detect_video(video_path, conf_threshold):
    """Detect and track hen combs across video frames with custom Neon Green boxes and centroid tracking."""
    if not video_path or not os.path.exists(video_path):
        return None, "No video provided"
        
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    
    output_path = "output_green_tracked.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    # Centroid tracker across frames to give stable unique IDs
    next_hen_id = 1
    tracked_hens = {}  # {id: (cx, cy, last_seen_frame)}
    MAX_DISTANCE = 45  # pixels
    
    frame_idx = 0
    max_live_heads = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        results = model.predict(source=frame, conf=conf_threshold, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []
        scores = results[0].boxes.conf.cpu().numpy() if results[0].boxes is not None else []
        
        # Match detections to existing tracked hens
        current_centroids = []
        for b in boxes:
            cx = int((b[0] + b[2]) / 2)
            cy = int((b[1] + b[3]) / 2)
            current_centroids.append((cx, cy))
            
        matched_ids = []
        unmatched_indices = list(range(len(current_centroids)))
        
        for hid, (hx, hy, _) in list(tracked_hens.items()):
            best_dist = float('inf')
            best_idx = -1
            for idx in unmatched_indices:
                cx, cy = current_centroids[idx]
                dist = math.hypot(cx - hx, cy - hy)
                if dist < best_dist and dist < MAX_DISTANCE:
                    best_dist = dist
                    best_idx = idx
            if best_idx != -1:
                tracked_hens[hid] = (current_centroids[best_idx][0], current_centroids[best_idx][1], frame_idx)
                matched_ids.append((best_idx, hid))
                unmatched_indices.remove(best_idx)
                
        for idx in unmatched_indices:
            tracked_hens[next_hen_id] = (current_centroids[idx][0], current_centroids[idx][1], frame_idx)
            matched_ids.append((idx, next_hen_id))
            next_hen_id += 1
            
        matched_ids.sort(key=lambda x: x[0])
        ordered_ids = [item[1] for item in matched_ids]
        
        # Draw frame with custom neon green boxes and unique HEAD IDs
        display = frame.copy()
        for i, box in enumerate(boxes):
            hid = ordered_ids[i] if i < len(ordered_ids) else (i + 1)
            x1, y1, x2, y2 = map(int, box[:4])
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(0, min(width - 1, x2))
            y2 = max(0, min(height - 1, y2))
            bw, bh = x2 - x1, y2 - y1
            if bw < 4 or bh < 4:
                continue
                
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            
            # 1. Neon Green box outline
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # 2. White corner brackets
            c_len = max(5, int(min(bw, bh) * 0.28))
            for px, py, dx, dy in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
                cv2.line(display, (px, py), (px + dx * c_len, py), (255, 255, 255), 2, cv2.LINE_AA)
                cv2.line(display, (px, py), (px, py + dy * c_len), (255, 255, 255), 2, cv2.LINE_AA)
                
            # 3. Center target reticle dot
            cv2.circle(display, (cx, cy), 3, (0, 255, 0), -1)
            cv2.circle(display, (cx, cy), 1, (255, 255, 255), -1)
            
            # 4. Solid green badge HEAD #{hid} with black text
            lbl_text = f"HEAD #{hid}"
            (tw, th), _ = cv2.getTextSize(lbl_text, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
            badge_y1 = max(0, y1 - th - 6)
            badge_y2 = y1
            badge_x1 = x1
            badge_x2 = min(width - 1, x1 + tw + 8)
            cv2.rectangle(display, (badge_x1, badge_y1), (badge_x2, badge_y2), (0, 255, 0), -1)
            cv2.putText(display, lbl_text, (badge_x1 + 4, badge_y2 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1, cv2.LINE_AA)
            
        # Top-Left Telemetry HUD Card
        hud_w = 210
        hud_h = 75
        cv2.rectangle(display, (8, 12), (8 + hud_w, 12 + hud_h), (0, 0, 0), -1)
        cv2.rectangle(display, (8, 12), (8 + hud_w, 12 + hud_h), (0, 255, 0), 1)
        
        cv2.putText(display, f"TIME: {frame_idx/fps:.1f}s / {total_frames/fps:.1f}s", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)
        cv2.putText(display, f"HEN HEADS: {len(boxes)}", (14, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(display, f"TOTAL COUNTED: {next_hen_id - 1}", (14, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 215, 255), 2, cv2.LINE_AA)
        
        out.write(display)
        
        if len(boxes) > max_live_heads:
            max_live_heads = len(boxes)
            
        frame_idx += 1
        
    cap.release()
    out.release()
    
    summary = f"✅ Video Processed: {frame_idx} frames | Unique Hens Tagged: {next_hen_id - 1} | Max Visible Combs: {max_live_heads}"
    return output_path, summary


# Build Gradio UI
with gr.Blocks(title="🐔 Hen Comb Detection & Counter (YOLOv8)", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🐔 GioTag — Hen Comb AI Detection & Tracking")
    gr.Markdown("Real-time AI Hen Comb detection with **Studio Neon Green Bounding Boxes**, HEAD badges, and Telemetry HUD powered by `best.pt`.")
    
    with gr.Tab("🖼️ Image Detection"):
        with gr.Row():
            with gr.Column():
                img_in = gr.Image(type="numpy", label="Upload Hen Image / Photo")
                img_slider = gr.Slider(minimum=0.05, maximum=0.95, value=0.25, step=0.05, label="Detection Confidence Threshold")
                img_btn = gr.Button("🔍 Detect Hen Combs (Green Boxes)", variant="primary")
            with gr.Column():
                img_out = gr.Image(label="Annotated Detections (Neon Green Studio UI)")
                img_msg = gr.Textbox(label="Count Summary")
        img_btn.click(fn=detect_image, inputs=[img_in, img_slider], outputs=[img_out, img_msg])

    with gr.Tab("🎥 Video Detection"):
        with gr.Row():
            with gr.Column():
                vid_in = gr.Video(label="Upload Hen Video (MP4)")
                vid_slider = gr.Slider(minimum=0.05, maximum=0.95, value=0.25, step=0.05, label="Detection Confidence Threshold")
                vid_btn = gr.Button("⚡ Track Video Combs (Green Boxes & HUD)", variant="primary")
            with gr.Column():
                vid_out = gr.Video(label="Annotated Video Output")
                vid_msg = gr.Textbox(label="Video Tracking Summary")
        vid_btn.click(fn=detect_video, inputs=[vid_in, vid_slider], outputs=[vid_out, vid_msg])
        
        if os.path.exists("demo_hen_video.mp4"):
            gr.Examples(
                examples=[["demo_hen_video.mp4", 0.25]],
                inputs=[vid_in, vid_slider],
                label="Sample Test Video"
            )

if __name__ == "__main__":
    demo.launch()
