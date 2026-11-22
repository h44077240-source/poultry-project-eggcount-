import os
from huggingface_hub import HfApi

TOKEN = os.environ.get("HF_TOKEN", "")
REPO_ID = "sachin5644/giotag-backend"

app_py = """import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("CORS_ORIGINS", "*")
os.environ.setdefault("RENDER", "false")

try:
    import spaces
    @spaces.GPU
    def zero_gpu_anchor():
        return "ZeroGPU Active"
    zero_gpu_anchor()
except Exception as e:
    print(f"ZeroGPU init: {e}")

import uvicorn
import gradio as gr
from app.main import app as fastapi_app

with gr.Blocks(title="GioTag Poultry AI Vision Server") as demo:
    gr.Markdown("# 🐔 GioTag AI Poultry Vision Server\\n### 🟢 Online (ZeroGPU / 16 GB RAM • High-Speed)")

app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
"""

api = HfApi(token=TOKEN)
api.upload_file(
    path_or_fileobj=app_py.encode('utf-8'),
    path_in_repo="app.py",
    repo_id=REPO_ID,
    repo_type="space"
)
print("Uploaded app.py with @spaces.GPU anchor!")
api.restart_space(repo_id=REPO_ID)
print("Space restarted!")
