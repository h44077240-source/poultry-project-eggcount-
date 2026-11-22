import os
import shutil
from pathlib import Path
from huggingface_hub import HfApi

TOKEN = os.environ.get("HF_TOKEN", "")
REPO_ID = "sachin5644/giotag-backend"

src_backend = Path("backend")
deploy_dir = Path("hf_deploy")
if deploy_dir.exists():
    shutil.rmtree(deploy_dir)
deploy_dir.mkdir(parents=True, exist_ok=True)

# 1. Copy app directory
shutil.copytree(src_backend / "app", deploy_dir / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

# 2. Copy models & assets
for fname in ["best_quant.onnx", "best.pt", "demo_hen_video.mp4", "flask_app.py"]:
    src_file = src_backend / fname
    if src_file.exists():
        shutil.copy2(src_file, deploy_dir / fname)
        print(f"Copied {fname}: {src_file.stat().st_size / (1024*1024):.1f} MB")

# 3. Create app.py
app_py = """import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("CORS_ORIGINS", "*")
os.environ.setdefault("RENDER", "false")

import uvicorn
import gradio as gr
from app.main import app as fastapi_app

with gr.Blocks(title="GioTag Poultry AI Vision Server") as demo:
    gr.Markdown(\"\"\"
    # 🐔 GioTag AI Poultry Vision Server
    ### 🟢 Online (16 GB RAM • High-Speed CPU)
    
    This server powers real-time Hen Comb AI tracking and Egg Tray counting.
    - Hen Comb Stream: `/api/tracker/stream_video`
    - Live Frame API: `/api/tracker/live_frame`
    - Stream Count: `/api/tracker/stream_count`
    - Swagger Documentation: `/docs`
    \"\"\")

app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
"""
with open(deploy_dir / "app.py", "w", encoding="utf-8") as f:
    f.write(app_py)

# 4. packages.txt
packages_txt = """ffmpeg
libsm6
libxext6
libgl1-mesa-glx
libglib2.0-0
libpq-dev
"""
with open(deploy_dir / "packages.txt", "w", encoding="utf-8") as f:
    f.write(packages_txt)

# 5. requirements.txt
reqs = """fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
pydantic>=2.7.1
pydantic-settings>=2.3.0
email-validator>=2.1.1
sqlalchemy>=2.0.30
alembic>=1.13.1
psycopg2-binary>=2.9.9
opencv-python-headless>=4.9.0.80
Pillow>=11.1.0
numpy>=1.26.4
ultralytics
onnxruntime>=1.19.0
cryptography>=42.0.7
bcrypt>=4.0.1
httpx>=0.27.0
python-dateutil>=2.9.0
pytz>=2024.1
python-dotenv>=1.0.1
piexif
pillow-heif>=1.1.1
Flask>=3.0.3
Flask-Cors>=4.0.0
gradio>=4.0.0
"""
with open(deploy_dir / "requirements.txt", "w", encoding="utf-8") as f:
    f.write(reqs)

# 6. README.md with YAML metadata
readme_md = """---
title: Giotag Backend
emoji: 🐔
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.20.1
python_version: '3.11'
app_file: app.py
pinned: false
license: mit
---

# GioTag AI Vision Server (16 GB RAM)
Real-time Hen Comb AI detection and Egg Tray counting backend.
"""
with open(deploy_dir / "README.md", "w", encoding="utf-8") as f:
    f.write(readme_md)

print("hf_deploy directory assembled successfully!")
print("Starting upload to Hugging Face Spaces via HfApi...")

api = HfApi(token=TOKEN)
api.upload_folder(
    folder_path=str(deploy_dir),
    repo_id=REPO_ID,
    repo_type="space",
    commit_message="Deploy GioTag AI Backend to Hugging Face Spaces (16 GB RAM)"
)
print("Upload completed successfully to https://huggingface.co/spaces/" + REPO_ID)
