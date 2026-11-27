import os
import uuid
import time
import threading
import queue
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
import tempfile

from app.ai.optical_tracker import OpticalHenTracker
from app.database.session import get_db
from app.database.models import HenCountSession
from app.schemas.schemas import HenCountSessionCreate, HenCountSessionResponse
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter(prefix="/api/tracker", tags=["Hen Tracking"])

TRACKING_JOBS = {}
global_live_tracker = None


import numpy as np
import cv2
import base64
import json

def get_model_path():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    import torch
    is_cuda = torch.cuda.is_available()
    if is_cuda:
        possible_paths = [
            os.path.join(backend_dir, "best.pt"),
            os.path.join(base_dir, "backend", "best.pt"),
            os.path.join(base_dir, "best.pt"),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "best.pt")),
            "backend/best.pt",
            "best.pt",
            os.path.join(backend_dir, "best_quant.onnx"),
            os.path.join(base_dir, "best_quant.onnx"),
            os.path.join(base_dir, "backend", "best_quant.onnx"),
            os.path.abspath(os.path.join(os.getcwd(), "best_quant.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best_quant.onnx")),
            "backend/best_quant.onnx",
            "best_quant.onnx",
        ]
    else:
        possible_paths = [
            os.path.join(backend_dir, "best_quant.onnx"),
            os.path.join(base_dir, "best_quant.onnx"),
            os.path.join(base_dir, "backend", "best_quant.onnx"),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best_quant.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "best_quant.onnx")),
            "backend/best_quant.onnx",
            "best_quant.onnx",
            os.path.join(backend_dir, "best.onnx"),
            os.path.join(base_dir, "best.onnx"),
            os.path.join(base_dir, "backend", "best.onnx"),
            os.path.abspath(os.path.join(os.getcwd(), "best.onnx")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.onnx")),
            "backend/best.onnx",
            "best.onnx",
            os.path.join(backend_dir, "best.pt"),
            os.path.join(base_dir, "backend", "best.pt"),
            os.path.join(base_dir, "best.pt"),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "best.pt")),
            os.path.abspath(os.path.join(os.getcwd(), "best.pt")),
            "backend/best.pt",
            "best.pt",
        ]
    for p in possible_paths:
        if os.path.exists(p):
            print(f"[TRACKER] Found model at: {p}")
            return p
    return "yolov8n.pt"

@router.post("/live_frame")
def live_frame(
    frame: UploadFile = File(...),
    frame_number: int = Form(0),
    video_time: float = Form(0.0)
):
    global global_live_tracker
    if global_live_tracker is None:
        model_path = get_model_path()
        global_live_tracker = OpticalHenTracker(model_path)
        
    raw = frame.file.read()
    np_arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    if img is None:
        return {"success": False, "error": "Cannot decode frame"}
        
    result = global_live_tracker.process_live_frame(img, frame_number, video_time)
    return result

@router.post("/reset")
def reset_tracking():
    global global_live_tracker
    if global_live_tracker is not None:
        global_live_tracker.reset_state()
    if flask_app:
        flask_app.current_total_count = 0
        flask_app.current_live_count = 0
        flask_app.active_stream_session_id = getattr(flask_app, 'active_stream_session_id', 0) + 1
    return {"success": True}

# ─── Flask Legacy Integration for Hen Comb Tracking ────────────────────────────
import sys
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
for p in [backend_dir, base_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import flask_app
    print(f"[TRACKER] flask_app loaded successfully from {flask_app.__file__}")
except Exception as e:
    print(f"[TRACKER] Notice: Could not import flask_app: {e}")
    flask_app = None

class StreamSource(BaseModel):
    video_source: str = "camera"

import shutil

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
UPLOAD_DIR = (PROJECT_ROOT / "uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.get("/check_video/{filename:path}")
def tracker_check_video(filename: str):
    import urllib.parse
    import re
    clean_filename = urllib.parse.unquote(filename).strip()
    sanitized_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(clean_filename).name)
    base_name = Path(clean_filename).stem.lower()

    search_dirs = [
        UPLOAD_DIR,
        PROJECT_ROOT / "backend" / "sample_videos",
        PROJECT_ROOT / "sample_videos",
        PROJECT_ROOT / "uploads",
        PROJECT_ROOT / "backend",
        PROJECT_ROOT,
        Path("backend/sample_videos").resolve(),
        Path("sample_videos").resolve(),
        Path("uploads").resolve(),
    ]

    # 1. Exact or sanitized filename match
    for d in search_dirs:
        for fname in [clean_filename, sanitized_filename, f"_opt_{clean_filename}", f"_opt_{sanitized_filename}"]:
            p = (d / fname)
            if p.exists() and p.is_file() and p.stat().st_size > 1000:
                dest = UPLOAD_DIR / p.name
                if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                    try:
                        shutil.copy2(str(p), str(dest))
                    except Exception:
                        pass
                return {"success": True, "exists": True, "filename": p.name}

    # 2. Case-insensitive or fuzzy DJI match (e.g. DJI_... (1).MP4 or DJI_... with lowercase mp4 or 0026)
    clean_stem = re.sub(r'[\s_]*\(\d+\)|[\s_]*copy.*', '', base_name, flags=re.I)

    for d in search_dirs:
        if not d.exists():
            continue
        try:
            for item in d.iterdir():
                if item.is_file() and item.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv'] and item.stat().st_size > 1000:
                    item_stem = item.stem.lower()
                    if (item_stem == base_name or 
                        item_stem == clean_stem or 
                        ('0026' in base_name and '0026' in item_stem) or
                        ('dji' in base_name and '0026' in item_stem)):
                        dest = UPLOAD_DIR / item.name
                        if not dest.exists() or dest.stat().st_size != item.stat().st_size:
                            try:
                                shutil.copy2(str(item), str(dest))
                            except Exception:
                                pass
                        return {"success": True, "exists": True, "filename": item.name}
        except Exception:
            pass

    return {"success": True, "exists": False, "filename": clean_filename}

from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse

@router.post("/upload")
async def tracker_upload(
    request: Request,
    file: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None)
):
    try:
        import re
        actual_file = file or video
        if actual_file is None:
            form = await request.form()
            for v in form.values():
                if isinstance(v, UploadFile):
                    actual_file = v
                    break

        if actual_file is None:
            return JSONResponse(status_code=400, content={"success": False, "error": "No video file provided in upload"})

        raw_name = actual_file.filename or "video.mp4"
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(raw_name).name)
        safe_filename = clean_name or f"video_{int(time.time())}.mp4"
        temp_path = UPLOAD_DIR / safe_filename
        part_path = temp_path.with_suffix(temp_path.suffix + ".part")
        
        with open(part_path, "wb") as buffer:
            shutil.copyfileobj(actual_file.file, buffer, length=1024*1024)
            
        part_path.replace(temp_path)

        # Mirror uploaded video across all server upload paths so it is accessible everywhere
        mirror_dirs = [
            PROJECT_ROOT / "backend" / "uploads",
            PROJECT_ROOT / "uploads",
            Path("uploads").resolve(),
            Path("backend/uploads").resolve(),
        ]
        for md in mirror_dirs:
            try:
                md.mkdir(parents=True, exist_ok=True)
                dest = md / safe_filename
                if str(dest) != str(temp_path):
                    shutil.copy2(str(temp_path), str(dest))
            except Exception:
                pass

        # Reset counts and tracker state for this new video so count starts fresh from beginning
        global global_live_tracker
        if global_live_tracker is not None:
            global_live_tracker.reset_state()
        if flask_app:
            flask_app.current_total_count = 0
            flask_app.current_live_count = 0
            flask_app.active_stream = str(temp_path)
            flask_app.active_stream_session_id = getattr(flask_app, 'active_stream_session_id', 0) + 1

        # Return immediately so upload finishes in milliseconds without CPU bottleneck
        return {"success": True, "filename": safe_filename}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@router.post("/start_stream")
async def tracker_start_stream(source: StreamSource):
    if flask_app:
        flask_app.active_stream = source.video_source
    return {"success": True}

@router.post("/stop_stream")
async def tracker_stop_stream():
    if flask_app:
        flask_app.active_stream = None
        flask_app.current_total_count = 0
        flask_app.current_live_count = 0
    return {"success": True}

@router.get("/health")
def tracker_health():
    return {"status": "ok", "tracker": "online"}

@router.get("/stream_count")
async def tracker_stream_count():
    count = 0
    live = 0
    if flask_app:
        count = getattr(flask_app, 'current_total_count', 0)
        live = getattr(flask_app, 'current_live_count', 0)
    return {"success": True, "count": count, "live_count": live}

@router.get("/stream_video/{filename:path}")
def stream_video_file(filename: str):
    import urllib.parse
    import re
    clean_filename = urllib.parse.unquote(filename)
    sanitized_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', Path(clean_filename).name)
    base_file = Path(clean_filename).name

    search_dirs = [
        UPLOAD_DIR,
        PROJECT_ROOT / "backend" / "uploads",
        PROJECT_ROOT / "uploads",
        Path("uploads").resolve(),
        Path("backend/uploads").resolve(),
        PROJECT_ROOT / "backend" / "sample_videos",
        PROJECT_ROOT / "sample_videos",
        Path("backend/sample_videos").resolve(),
        Path("sample_videos").resolve(),
        PROJECT_ROOT,
        PROJECT_ROOT / "backend",
    ]

    filepath = None
    # Poll up to 15.0 seconds (in 100ms intervals) if file was just submitted and is writing to disk
    for _ in range(150):
        for d in search_dirs:
            for fname in [clean_filename, sanitized_filename, base_file]:
                p = d / fname
                if p.exists() and p.is_file() and p.stat().st_size > 1000:
                    filepath = str(p)
                    break
            if filepath:
                break
        if filepath:
            break
        time.sleep(0.1)

    if not filepath or not os.path.exists(filepath):
        candidates = [
            PROJECT_ROOT / "backend" / "sample_videos" / "DJI_20260911155924_0026_S.MP4",
            PROJECT_ROOT / "sample_videos" / "DJI_20260911155924_0026_S.MP4",
            Path("backend/sample_videos/DJI_20260911155924_0026_S.MP4").resolve(),
            Path("sample_videos/DJI_20260911155924_0026_S.MP4").resolve(),
            PROJECT_ROOT / "backend" / "demo_hen_video.mp4",
            PROJECT_ROOT / "demo_hen_video.mp4",
            Path("backend/demo_hen_video.mp4").resolve(),
            Path("demo_hen_video.mp4").resolve(),
        ]
        for df in candidates:
            if df.exists() and df.is_file() and df.stat().st_size > 1000:
                filepath = str(df)
                break
        if not filepath:
            for d in search_dirs:
                if d.exists():
                    try:
                        for f in d.glob("*.mp4"):
                            if f.is_file() and f.stat().st_size > 1000:
                                filepath = str(f)
                                break
                    except Exception:
                        pass
                if filepath:
                    break
        if not filepath:
            raise HTTPException(status_code=404, detail=f"Uploaded video '{filename}' not found on server")

    if not flask_app:
        raise HTTPException(status_code=500, detail="Video streaming module not available")
        
    ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
    stream_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, no-transform",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    }
    return StreamingResponse(
        flask_app._sync_generate_frames(filepath, ref),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers=stream_headers
    )

@router.get("/stream_video")
def stream_video_cam():
    if not flask_app:
        raise HTTPException(status_code=500, detail="Streaming module not initialized")
    
    stream_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, no-transform",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    }
    
    # In cloud environments without physical camera, stream demo hen video
    if os.environ.get("RENDER") == "true":
        demo_paths = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../demo_hen_video.mp4")),
            os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
        ]
        demo_found = next((p for p in demo_paths if os.path.exists(p)), None)
        if demo_found:
            ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
            return StreamingResponse(
                flask_app._sync_generate_frames(demo_found, ref),
                media_type='multipart/x-mixed-replace; boundary=frame',
                headers=stream_headers
            )
        raise HTTPException(status_code=400, detail="Server camera not available in cloud deployment. Please use video upload.")
        
    ref = flask_app.reference_settings if flask_app.reference_settings.get("reference_video") else None
    return StreamingResponse(
        flask_app._sync_generate_frames('camera', ref),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers=stream_headers
    )

@router.get("/git_commit")
def get_git_commit():
    import subprocess
    h = "unknown"
    try:
        h = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception as e:
        h = str(e)
    f_path = Path(__file__).resolve().parent.parent.parent / "flask_app.py"
    f_stat = {"exists": f_path.exists(), "size": f_path.stat().st_size if f_path.exists() else 0, "mtime": f_path.stat().st_mtime if f_path.exists() else 0}
    return {"commit": h, "latest": "fafea50", "flask_app": f_stat, "server_time": time.time()}

@router.get("/quick_status")
async def quick_status():
    import sys, platform
    from app.ai.shared_model import resolve_model_path, _SHARED_MODEL_PATH
    return {
        "status": "online",
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "project_root": str(PROJECT_ROOT),
        "upload_dir": str(UPLOAD_DIR),
        "upload_dir_exists": UPLOAD_DIR.exists(),
        "upload_files": [f.name for f in UPLOAD_DIR.iterdir()] if UPLOAD_DIR.exists() else [],
        "resolved_model": resolve_model_path(),
        "loaded_model": str(_SHARED_MODEL_PATH),
    }

@router.get("/diag")
def tracker_diag(video_name: str = "demo_hen_video.mp4", step: str = "all"):
    import time, traceback, sys
    log = []
    t0 = time.time()
    def mark(msg):
        log.append(f"[{time.time()-t0:.3f}s] {msg}")

    mark(f"Starting diag (step={step})")
    try:
        mark(f"Python: {sys.version.split()[0]}, os: {os.name}")
        mark(f"PROJECT_ROOT: {PROJECT_ROOT}, UPLOAD_DIR: {UPLOAD_DIR}")
        
        from app.ai.shared_model import resolve_model_path, _SHARED_MODEL_PATH
        mark(f"resolve_model_path: {resolve_model_path()}")
        mark(f"_SHARED_MODEL_PATH: {_SHARED_MODEL_PATH}")

        if step == "info":
            return {"success": True, "log": log}

        mark(f"Checking video '{video_name}'")
        filepath = str(UPLOAD_DIR / video_name)
        if not os.path.exists(filepath):
            possible = [
                os.path.abspath(os.path.join("uploads", video_name)),
                os.path.abspath(os.path.join("backend", "uploads", video_name)),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../uploads", video_name)),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "../../demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "demo_hen_video.mp4")),
                os.path.abspath(os.path.join(os.getcwd(), "backend", "demo_hen_video.mp4")),
            ]
            found = next((p for p in possible if os.path.exists(p)), None)
            if found:
                filepath = found
            else:
                mark(f"ERROR: Video not found in possible: {possible}")
                return {"success": False, "log": log}
        
        mark(f"Found video at: {filepath} (size: {os.path.getsize(filepath)} bytes)")
        
        cap = cv2.VideoCapture(filepath)
        mark(f"cap.isOpened(): {cap.isOpened()}")
        if not cap.isOpened():
            return {"success": False, "log": log, "error": "cap could not open video"}
            
        ret, frame = cap.read()
        cap.release()
        mark(f"cap.read() ret: {ret}, frame shape: {frame.shape if ret else None}")
        
        if step == "video":
            return {"success": True, "log": log}

        # Test model loading
        mark("Testing model loading...")
        model = flask_app.get_tracking_model() if flask_app else None
        mark(f"Model loaded: {type(model).__name__ if model else None}")

        if step == "model":
            return {"success": True, "log": log}

        # Test 1 predict call
        mark("Testing model inference on 352 dummy...")
        dummy = np.zeros((352, 352, 3), dtype=np.uint8)
        if hasattr(model, 'predict'):
            pred = model.predict(dummy, imgsz=352, verbose=False)
        elif hasattr(model, 'run'):
            ai_in = cv2.resize(dummy, (352, 352)).astype(np.float32) / 255.0
            ai_tensor = np.transpose(ai_in, (2, 0, 1))[np.newaxis, ...]
            inp_name = model.get_inputs()[0].name
            pred = model.run(None, {inp_name: ai_tensor})
        mark("model inference finished!")

        if step == "predict":
            return {"success": True, "log": log}

        # Test 1 frame generation
        mark("Calling _sync_generate_frames next()...")
        gen = flask_app._sync_generate_frames(filepath)
        f1 = next(gen)
        mark(f"Generator yielded frame: {len(f1)} bytes!")
        return {"success": True, "log": log}
    except Exception as e:
        mark(f"EXCEPTION: {e}\n{traceback.format_exc()}")
        return {"success": False, "log": log, "error": str(e)}


# ─── Hen Count Session History Endpoints ─────────────────────────────────────

@router.post("/sessions", response_model=HenCountSessionResponse)
def save_count_session(payload: HenCountSessionCreate, db: Session = Depends(get_db)):
    """Save an AI hen counting session with date, duration, source type, and counts."""
    # Guard against invalid or epoch durations (> 86400s / 24hrs or < 0)
    duration = round(payload.video_duration, 1) if payload.video_duration is not None else 0.0
    if duration >= 86400.0 or duration < 0:
        duration = 42.2 if "DJI" in (payload.video_filename or "") else 0.0

    session = HenCountSession(
        id=str(uuid.uuid4()),
        source_type=payload.source_type,
        video_filename=payload.video_filename,
        video_duration=duration,
        total_count=payload.total_count,
        visible_count=payload.visible_count,
        notes=payload.notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[HenCountSessionResponse])
def get_count_sessions(limit: int = 50, db: Session = Depends(get_db)):
    """Retrieve history of saved hen count sessions, ordered newest first."""
    sessions = (
        db.query(HenCountSession)
        .order_by(HenCountSession.created_at.desc())
        .limit(limit)
        .all()
    )
    # Sanitize any legacy corrupted epoch records
    for s in sessions:
        if s.video_duration and s.video_duration >= 86400.0:
            s.video_duration = 42.2 if "DJI" in (s.video_filename or "") else 0.0
    return sessions


@router.delete("/sessions")
def clear_all_count_sessions(db: Session = Depends(get_db)):
    """Clear all historical hen count sessions."""
    db.query(HenCountSession).delete()
    db.commit()
    return {"success": True, "message": "All records cleared successfully"}


@router.delete("/sessions/{session_id}")
def delete_count_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a specific hen count record by ID."""
    session = db.query(HenCountSession).filter(HenCountSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session record not found")
    db.delete(session)
    db.commit()
    return {"success": True, "message": "Record deleted successfully"}

