import os
import sys

# Ensure backend and root directories are in python search path
backend_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(backend_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("CORS_ORIGINS", "*")

import uvicorn
import gradio as gr
from app.main import app as fastapi_app

# Interactive Status Banner on /ui
with gr.Blocks(title="GioTag AI Vision Server") as demo:
    gr.Markdown("""
    # 🐔 GioTag AI Hen Comb & Egg Tracking Server
    ### Status: 🟢 Online (16 GB RAM • High-Speed CPU)
    
    This server powers real-time Hen Comb detection and Egg Tray counting for GioTag Poultry Farm.
    
    - **API Base**: `/`
    - **Hen Comb Stream**: `/api/tracker/stream_video`
    - **Live Frame API**: `/api/tracker/live_frame`
    - **Stream Count**: `/api/tracker/stream_count`
    - **API Documentation**: `/docs`
    """)

# Mount Gradio onto the existing FastAPI application at /ui
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
