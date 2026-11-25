"""
GioTag — Secure Geotagged Photo Capture & Monitoring System
FastAPI Backend Application
"""
import os
import tempfile
# Multi-threading optimization (set to 1 thread only in Render free tier 512MB RAM)
os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "Ultralytics"))
if os.environ.get("RENDER") == "true":
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
else:
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

from pathlib import Path
# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import JSONResponse
# pyrefly: ignore [missing-import]
from fastapi import HTTPException

from app.config import settings
from app.database.session import create_tables

# ─── Import all routers ───────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.devices import router as devices_router
from app.api.evidence import router as evidence_router
from app.api.gis import router as gis_router
from app.api.ai import router as ai_router
from app.api.blockchain import router as blockchain_router
from app.api.sync import router as sync_router
from app.api.audit import router as audit_router
from app.api.dashboard import router as dashboard_router
from app.api.reports import router as reports_router
from app.api.tracker import router as tracker_router
from app.api.farm_intelligence import router as farm_intelligence_router

# ─── App Factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Secure Geotagged Photo Capture & Monitoring System — "
        "Backend REST API providing JWT auth, evidence management, "
        "AI verification, blockchain hash registration, and GIS data."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Allows all origins (Render cloud, Vercel, localhost, local IP network)
cors_origins = settings.cors_origins_list

if "*" in cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"^https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

# ─── Static file serving for uploads ──────────────────────────────────────────
uploads_path = Path(settings.LOCAL_STORAGE_PATH)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

# ─── Register routers ─────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(devices_router)
app.include_router(evidence_router)
app.include_router(gis_router)
app.include_router(ai_router)
app.include_router(blockchain_router)
app.include_router(sync_router)
app.include_router(audit_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(tracker_router)
app.include_router(farm_intelligence_router)

# ─── Startup ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Initialize DB tables and seed demo data if configured."""
    create_tables()

    # ALWAYS run super admin health check — ensures login works in hosted environments
    # even after redeploys, DB migrations, or free-tier container restarts.
    try:
        from app.database.seed import ensure_super_admin_active
        ensure_super_admin_active()
    except Exception as e:
        print(f"[WARNING] Super admin health check failed: {e}")

    if settings.SEED_DEMO_DATA:
        try:
            from app.database.seed import seed
            seed()
        except Exception as e:
            print(f"Seed warning: {e}")

    # Initialize blockchain ledger (creates genesis block)
    try:
        from app.blockchain.ledger import blockchain
        print(f"[OK] Blockchain ledger ready ({blockchain.get_chain_length()} blocks)")
    except Exception as e:
        print(f"[WARNING] Blockchain init warning: {e}")

    # Preload shared AI model locally (on cloud containers like Railway/Render, defer to on-demand to keep container startup under 1s and avoid timeouts)
    if os.environ.get("RENDER") == "true" or os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME") or os.environ.get("PORT"):
        print("[START] Cloud container active: YOLO model will load on-demand (<1s startup).")
    else:
        try:
            from app.ai.shared_model import get_shared_model
            import gc
            print("[START] Initializing shared singleton YOLO model...")
            get_shared_model()
            gc.collect()
            print("[OK] Shared YOLO model ready")
        except Exception as e:
            print(f"[WARNING] YOLO model preload note: {e}")

    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} started ({settings.ENVIRONMENT})")


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


# ─── Static Frontend Serving (SPA) ──────────────────────────────────────────
from fastapi.responses import FileResponse, StreamingResponse, Response
import re

root_dir = Path(__file__).resolve().parent.parent.parent
possible_dirs = [
    Path(__file__).resolve().parent.parent / "static",
    root_dir / "frontend" / "dist",
    root_dir / "dist",
]
static_dir = next((d for d in possible_dirs if d.exists() and (d / "index.html").exists()), None)

MEDIA_EXTENSIONS = {
    ".mp4", ".webm", ".ogg", ".mp3", ".wav",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp",
    ".css", ".js", ".mjs", ".map", ".json",
    ".woff", ".woff2", ".ttf", ".eot"
}

def stream_file_with_range(path: Path, request: Request, media_type: str = "video/mp4"):
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(str(path), media_type=media_type)
    
    range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        return FileResponse(str(path), media_type=media_type)
    
    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
    if start >= file_size or end >= file_size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
    
    chunk_size = (end - start) + 1
    
    def file_iterator():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                read_len = min(64 * 1024, remaining)
                data = f.read(read_len)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": media_type,
    }
    return StreamingResponse(file_iterator(), status_code=206, headers=headers)

if static_dir and (static_dir / "index.html").exists():
    if (static_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="static_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_frontend(request: Request, full_path: str):
        # Allow API routes, docs, and uploads to pass through
        if (full_path.startswith("api/") or 
            full_path.startswith("docs") or 
            full_path.startswith("redoc") or 
            full_path.startswith("openapi.json") or
            full_path.startswith("uploads/")):
            raise HTTPException(status_code=404, detail="Not Found")
        
        target = static_dir / full_path
        if target.is_file():
            ext = target.suffix.lower()
            if ext in {".mp4", ".webm"}:
                return stream_file_with_range(target, request, media_type=f"video/{ext[1:]}")
            return FileResponse(str(target))

        # If a specific static asset with known extension was requested but doesn't exist, return 404 (do not return index.html)
        req_ext = Path(full_path).suffix.lower()
        if req_ext in MEDIA_EXTENSIONS:
            return Response(status_code=404, content=f"Asset {full_path} not found", media_type="text/plain")

        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
else:
    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": f"Welcome to {settings.APP_NAME}",
            "docs": "/docs",
            "version": settings.APP_VERSION,
        }


# ─── Global error handler ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    
    import traceback
    traceback.print_exc()
    
    if settings.DEBUG:
        return JSONResponse(status_code=500, content={"detail": str(exc), "type": type(exc).__name__})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
