import os
from huggingface_hub import HfApi

TOKEN = os.environ.get("HF_TOKEN", "")
REPO_ID = "sachin5644/giotag-backend"

api = HfApi(token=TOKEN)

# 1. Clean requirements.txt with only essential tracker packages
reqs = """fastapi>=0.110.0
uvicorn[standard]>=0.28.0
python-multipart
pydantic>=2.0.0
pydantic-settings
opencv-python-headless
Pillow
numpy
ultralytics
onnxruntime
httpx
python-dotenv
Flask
Flask-Cors
"""

# 2. README.md without pinned buggy sdk_version
readme_md = """---
title: Giotag Backend
emoji: 🐔
colorFrom: green
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
license: mit
---

# GioTag AI Vision Server (16 GB RAM)
Real-time Hen Comb AI detection and Egg Tray counting backend.
"""

# 3. Empty packages.txt (no unnecessary apt packages)
packages_txt = ""

api.upload_file(
    path_or_fileobj=reqs.encode('utf-8'),
    path_in_repo="requirements.txt",
    repo_id=REPO_ID,
    repo_type="space"
)
print("Uploaded clean requirements.txt")

api.upload_file(
    path_or_fileobj=readme_md.encode('utf-8'),
    path_in_repo="README.md",
    repo_id=REPO_ID,
    repo_type="space"
)
print("Uploaded README.md")

api.upload_file(
    path_or_fileobj=packages_txt.encode('utf-8'),
    path_in_repo="packages.txt",
    repo_id=REPO_ID,
    repo_type="space"
)
print("Uploaded packages.txt")

api.restart_space(repo_id=REPO_ID)
print("Restarted Space! Building...")
