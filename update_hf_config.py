import os
import shutil
from pathlib import Path
from huggingface_hub import HfApi

TOKEN = os.environ.get("HF_TOKEN", "")
REPO_ID = "sachin5644/giotag-backend"

deploy_dir = Path("hf_deploy")
deploy_dir.mkdir(parents=True, exist_ok=True)

# 1. packages.txt (Debian 12 compatible - libgl1-mesa-glx removed)
packages_txt = """ffmpeg
libpq-dev
"""
with open(deploy_dir / "packages.txt", "w", encoding="utf-8") as f:
    f.write(packages_txt)

# 2. requirements.txt (clean, unpinned dependencies)
reqs = """fastapi
uvicorn[standard]
python-multipart
python-jose[cryptography]
passlib[bcrypt]
pydantic
pydantic-settings
email-validator
sqlalchemy
alembic
psycopg2-binary
opencv-python-headless
Pillow
numpy<2.0.0
ultralytics
onnxruntime
cryptography
bcrypt
httpx
python-dateutil
pytz
python-dotenv
Flask
Flask-Cors
"""
with open(deploy_dir / "requirements.txt", "w", encoding="utf-8") as f:
    f.write(reqs)

# 3. README.md with YAML metadata
readme_md = """---
title: Giotag Backend
emoji: 🐔
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.20.1
app_file: app.py
pinned: false
license: mit
---

# GioTag AI Vision Server (16 GB RAM)
Real-time Hen Comb AI detection and Egg Tray counting backend.
"""
with open(deploy_dir / "README.md", "w", encoding="utf-8") as f:
    f.write(readme_md)

print("Updated packages.txt and requirements.txt!")
print("Re-uploading configuration to Hugging Face Spaces...")

api = HfApi(token=TOKEN)
# Upload just the updated config files (models are already in Git LFS on the space!)
for fname in ["packages.txt", "requirements.txt", "README.md"]:
    api.upload_file(
        path_or_fileobj=str(deploy_dir / fname),
        path_in_repo=fname,
        repo_id=REPO_ID,
        repo_type="space"
    )
    print(f"Uploaded {fname}")

print("Upload completed! Hugging Face is rebuilding the space...")
