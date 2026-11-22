import os
import sys
import time
import tempfile
import cv2
import numpy as np

# 1. ZeroGPU must be imported before torch or CUDA libraries
import spaces

# Set optimal threads and environment
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import torch
import gradio as gr
from ultralytics import YOLO

# 2. Load Models
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "best.pt")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = "best.pt"

print(f"[STARTUP] Loading YOLO model from {MODEL_PATH}...")
try:
    yolo_model = YOLO(MODEL_PATH)
    print("[STARTUP] YOLO model loaded successfully!")
except Exception as e:
    print(f"[STARTUP WARN] Could not load YOLO from {MODEL_PATH}: {e}")
    yolo_model = None

# Import Egg Counter
try:
    from app.ai.egg_counter import count_objects_in_image
    print("[STARTUP] Egg counter module loaded!")
except Exception as e:
    print(f"[STARTUP WARN] Egg counter import note: {e}")
    count_objects_in_image = None


# ─── AI FUNCTIONS WITH ZeroGPU ───────────────────────────────────────────────

@spaces.GPU
def detect_hen_combs_image(input_img, conf_threshold=0.25):
    """Detects hen combs on a single image or camera snapshot."""
    if input_img is None:
        return None, "No image provided", 0

    if yolo_model is None:
        return input_img, "Model not loaded", 0

    # Ensure RGB
    if len(input_img.shape) == 2:
        img_rgb = cv2.cvtColor(input_img, cv2.COLOR_GRAY2RGB)
    else:
        img_rgb = input_img.copy()

    h, w = img_rgb.shape[:2]
    start_t = time.time()

    results = yolo_model.predict(
        source=img_rgb,
        conf=conf_threshold,
        iou=0.45,
        verbose=False
    )

    annotated = img_rgb.copy()
    count = 0

    for r in results:
        boxes = r.boxes
        for box in boxes:
            count += 1
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            
            # Draw snug bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 65), 2)
            
            # Draw label tag
            label = f"Hen #{count} ({conf:.0%})"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, max(0, y1 - 20)), (x1 + lw, y1), (0, 255, 65), -1)
            cv2.putText(annotated, label, (x1, max(14, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    elapsed = (time.time() - start_t) * 1000
    info_text = f"✅ Detected {count} Hens in {elapsed:.1f} ms | Resolution: {w}x{h}"
    return annotated, info_text, count


@spaces.GPU
def track_hen_combs_video(video_path, conf_threshold=0.25):
    """Processes video with YOLO and tracks hens over time."""
    if not video_path or not os.path.exists(video_path):
        return None, "Please select or upload a video file.", 0, 0, 0.0

    if yolo_model is None:
        return None, "YOLO model unavailable", 0, 0, 0.0

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, "Could not open video file.", 0, 0, 0.0

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    out_path = out_file.name
    out_file.close()

    # Use mp4v or avc1
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_writer = cv2.VideoWriter(out_path, fourcc, fps, (fw, fh))

    total_unique_hens = set()
    peak_visible = 0
    frame_idx = 0
    start_time = time.time()

    # Process video (sample if very long to stay within ZeroGPU limit)
    max_frames = min(total_frames, 600)  # up to 20-25 seconds of video
    step = 1 if total_frames <= 300 else 2

    while cap.isOpened() and frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if frame_idx % step != 0:
            continue

        results = yolo_model.track(
            source=frame,
            persist=True,
            conf=conf_threshold,
            iou=0.45,
            verbose=False
        )

        visible_in_frame = 0
        if results and len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                visible_in_frame += 1
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                track_id = int(box.id[0]) if box.id is not None else visible_in_frame
                total_unique_hens.add(track_id)
                
                # Draw box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 65), 2)
                tag = f"Hen #{track_id}"
                (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, max(0, y1 - 20)), (x1 + tw, y1), (0, 255, 65), -1)
                cv2.putText(frame, tag, (x1, max(14, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        peak_visible = max(peak_visible, visible_in_frame)

        # Overlay stats banner
        banner = f"Total Hens: {len(total_unique_hens)} | Visible: {visible_in_frame} | Frame: {frame_idx}/{max_frames}"
        cv2.putText(frame, banner, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(frame, banner, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        out_writer.write(frame)

    cap.release()
    out_writer.release()

    duration = time.time() - start_time
    calc_fps = round(frame_idx / max(0.1, duration), 1)
    status_summary = (
        f"✅ Tracking complete! Processed {frame_idx} frames in {duration:.1f}s ({calc_fps} FPS).\n"
        f"Total Unique Hens: {len(total_unique_hens)} | Peak Visible: {peak_visible}"
    )

    return out_path, status_summary, len(total_unique_hens), peak_visible, calc_fps


@spaces.GPU
def count_egg_tray(image):
    """Counts eggs in an egg tray using OpenCV Watershed and contour analysis."""
    if image is None:
        return None, "No image provided.", 0

    if count_objects_in_image is not None:
        try:
            # Convert numpy array to image bytes
            success, encoded_img = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            if success:
                res = count_objects_in_image(encoded_img.tobytes())
                count = res.get("count", 0)
                # Decode annotated image if present
                if "annotated_image" in res:
                    import base64
                    raw_b64 = res["annotated_image"].split(",")[-1]
                    ann_np = np.frombuffer(base64.b64decode(raw_b64), np.uint8)
                    annotated_bgr = cv2.imdecode(ann_np, cv2.IMREAD_COLOR)
                    annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
                    return annotated_rgb, f"✅ Detected {count} eggs in tray!", count
        except Exception as e:
            print(f"[EGG COUNTER NOTE] {e}")

    # Fallback OpenCV egg segmentation
    img_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
        param1=50, param2=30, minRadius=15, maxRadius=60
    )

    count = 0
    annotated = image.copy()
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            count += 1
            cv2.circle(annotated, (i[0], i[1]), i[2], (0, 255, 0), 2)
            cv2.circle(annotated, (i[0], i[1]), 2, (255, 0, 0), 3)

    return annotated, f"✅ Detected {count} eggs in tray!", count


# ─── GRADIO USER INTERFACE ───────────────────────────────────────────────────

custom_css = """
.main-title { font-size: 2.2rem; font-weight: 800; color: #10B981; margin-bottom: 0.2rem; }
.sub-title { font-size: 1.05rem; color: #9CA3AF; margin-bottom: 1rem; }
.metric-card { background: #1E293B; border-radius: 8px; padding: 12px; border: 1px solid #334155; }
"""

with gr.Blocks(title="GioTag AI Poultry Vision Server", css=custom_css, theme=gr.themes.Soft(primary_hue="emerald")) as demo:
    gr.HTML("""
    <div style="text-align: center; padding: 12px 0;">
        <div class="main-title">🐔 GioTag AI Poultry Vision Server</div>
        <div class="sub-title">16 GB RAM • Nvidia A10G Dedicated GPU • Real-time Hen Tracking & Egg Detection</div>
        <div style="display: flex; justify-content: center; gap: 10px; margin-top: 6px;">
            <span style="background: #065F46; color: #34D399; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">🟢 Online & Active</span>
            <span style="background: #1E3A8A; color: #60A5FA; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">⚡ ZeroGPU Accelerated</span>
            <span style="background: #374151; color: #E5E7EB; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">💾 16 GB High Memory</span>
        </div>
    </div>
    """)

    with gr.Tabs():
        # TAB 1: Video Tracking
        with gr.TabItem("🎥 Hen Comb Video Tracking"):
            gr.Markdown("### Upload Farm Video or Record Poultry Shed")
            with gr.Row():
                with gr.Column(scale=1):
                    video_input = gr.Video(label="Input Poultry Video", sources=["upload"])
                    demo_video_path = os.path.join(BASE_DIR, "demo_hen_video.mp4")
                    if os.path.exists(demo_video_path):
                        gr.Examples(
                            examples=[[demo_video_path, 0.25]],
                            inputs=[video_input],
                            label="📁 Click here to test with Demo Farm Video"
                        )
                    conf_slider = gr.Slider(minimum=0.10, maximum=0.90, value=0.25, step=0.05, label="Detection Confidence")
                    track_btn = gr.Button("🚀 Start AI Video Tracking", variant="primary", size="lg")

                with gr.Column(scale=1):
                    video_output = gr.Video(label="Processed Tracking Output", autoplay=True)
                    video_status = gr.Textbox(label="Processing Summary", lines=3)
                    with gr.Row():
                        metric_total = gr.Number(label="Total Unique Hens", value=0)
                        metric_peak = gr.Number(label="Peak Visible Hens", value=0)
                        metric_fps = gr.Number(label="Processing FPS", value=0.0)

            track_btn.click(
                fn=track_hen_combs_video,
                inputs=[video_input, conf_slider],
                outputs=[video_output, video_status, metric_total, metric_peak, metric_fps],
                api_name="track_video"
            )

        # TAB 2: Image Snapshot / Camera Frame
        with gr.TabItem("📸 Hen Comb Snapshot / Camera"):
            gr.Markdown("### Test Single Image or Phone Camera Frame")
            with gr.Row():
                with gr.Column(scale=1):
                    img_input = gr.Image(label="Hen Photo / Snapshot", sources=["upload", "webcam"], type="numpy")
                    img_conf = gr.Slider(minimum=0.10, maximum=0.90, value=0.25, step=0.05, label="Detection Confidence")
                    detect_btn = gr.Button("🔍 Detect Hens", variant="primary", size="lg")

                with gr.Column(scale=1):
                    img_output = gr.Image(label="Detection Result with Snug Boxes")
                    img_status = gr.Textbox(label="Status", lines=2)
                    img_count = gr.Number(label="Detected Hens Count", value=0)

            detect_btn.click(
                fn=detect_hen_combs_image,
                inputs=[img_input, img_conf],
                outputs=[img_output, img_status, img_count],
                api_name="detect_image"
            )

        # TAB 3: Egg Tray Counter
        with gr.TabItem("🥚 Egg Tray Counter"):
            gr.Markdown("### Automatic Egg Counting from Tray Photo")
            with gr.Row():
                with gr.Column(scale=1):
                    egg_input = gr.Image(label="Upload Egg Tray Photo", sources=["upload", "webcam"], type="numpy")
                    egg_btn = gr.Button("🥚 Count Eggs Now", variant="primary", size="lg")

                with gr.Column(scale=1):
                    egg_output = gr.Image(label="Annotated Egg Detections")
                    egg_status = gr.Textbox(label="Detection Results", lines=2)
                    egg_count_num = gr.Number(label="Total Eggs Counted", value=0)

            egg_btn.click(
                fn=count_egg_tray,
                inputs=[egg_input],
                outputs=[egg_output, egg_status, egg_count_num],
                api_name="count_eggs"
            )

        # TAB 4: API & System Diagnostics
        with gr.TabItem("⚡ Server Health & Specs"):
            gr.Markdown(f"""
            ### 🖥️ High-Performance Poultry AI Vision Server
            * **Space URL:** `https://sachin5644-giotag-backend.hf.space`
            * **Hardware:** Nvidia A10G Dedicated GPU + 16 GB RAM (ZeroGPU Free Tier)
            * **YOLO Weights:** `best.pt` (Loaded & Ready)
            * **Egg Detector:** OpenCV Watershed + Hough Circle Transform
            * **API Support:** Native Gradio Client API active at `/gradio_api`
            * **CORS:** Enabled for all origins (`*`)
            """)

if __name__ == "__main__":
    demo.queue().launch()
