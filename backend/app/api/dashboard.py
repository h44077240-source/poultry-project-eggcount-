"""Dashboard statistics API."""
from datetime import datetime, timedelta
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.session import get_db
from app.database.models import (
    User, Device, Evidence, BlockchainRecord,
    EvidenceStatusEnum, DeviceStatusEnum, BlockchainStatusEnum, RoleEnum
)
from app.schemas.schemas import DashboardStats
from app.security.rbac import require_admin_or_above

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/statistics", response_model=DashboardStats)
async def get_statistics(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    today = datetime.utcnow().date()
    week_ago = datetime.utcnow() - timedelta(days=7)

    ev_q = db.query(Evidence).filter(Evidence.deleted_at == None)

    # ─── Aggregate Today's Poultry Metrics ─────────────────────────────────────
    today_eggs = 0
    today_trays = 0
    today_missing = 0
    today_hens = 0
    try:
        from app.database.models import EggCountSession, HenCountSession
        egg_sessions_today = db.query(EggCountSession).filter(func.date(EggCountSession.created_at) == today).all()
        today_eggs = sum((s.egg_count or 0) for s in egg_sessions_today)
        today_trays = sum((s.tray_count or 0) for s in egg_sessions_today)
        today_missing = sum((s.missing_egg_count or 0) for s in egg_sessions_today)

        hen_sessions_today = db.query(HenCountSession).filter(func.date(HenCountSession.created_at) == today).all()
        today_hens = sum((s.total_count or 0) for s in hen_sessions_today)
    except Exception as e:
        print(f"[Dashboard Note] Poultry stats error: {e}")

    return DashboardStats(
        total_evidence=ev_q.count(),
        verified_evidence=ev_q.filter(Evidence.status == EvidenceStatusEnum.VERIFIED).count(),
        suspicious_evidence=ev_q.filter(Evidence.status == EvidenceStatusEnum.SUSPICIOUS).count(),
        pending_sync=ev_q.filter(Evidence.status == EvidenceStatusEnum.PENDING_SYNC).count(),
        active_users=db.query(User).filter(User.is_active == True, User.deleted_at == None).count(),
        registered_devices=db.query(Device).count(),
        authorized_devices=db.query(Device).filter(Device.status == DeviceStatusEnum.AUTHORIZED).count(),
        blockchain_records=db.query(BlockchainRecord).filter(
            BlockchainRecord.status == BlockchainStatusEnum.REGISTERED
        ).count(),
        evidence_today=ev_q.filter(func.date(Evidence.created_at) == today).count(),
        evidence_this_week=ev_q.filter(Evidence.created_at >= week_ago).count(),
        today_eggs=today_eggs,
        today_trays=today_trays,
        today_missing_eggs=today_missing,
        today_hens=today_hens,
    )


@router.get("/evidence-trend")
async def get_evidence_trend(
    days: int = 30,
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    """Return daily evidence counts for the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(func.date(Evidence.created_at).label("date"), func.count().label("count"))
        .filter(Evidence.created_at >= since, Evidence.deleted_at == None)
        .group_by(func.date(Evidence.created_at))
        .order_by(func.date(Evidence.created_at))
        .all()
    )
    return [{"date": str(r.date), "count": r.count} for r in rows]


@router.get("/status-distribution")
async def get_status_distribution(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    """Return evidence count by status."""
    rows = (
        db.query(Evidence.status, func.count().label("count"))
        .filter(Evidence.deleted_at == None)
        .group_by(Evidence.status)
        .all()
    )
    return [{"status": r.status.value, "count": r.count} for r in rows]


@router.get("/department-stats")
async def get_department_stats(
    current_user: User = Depends(require_admin_or_above),
    db: Session = Depends(get_db),
):
    """Return evidence count per department."""
    from app.database.models import Department
    rows = (
        db.query(Department.name, Department.code, func.count(Evidence.id).label("count"))
        .join(User, User.department_id == Department.id, isouter=True)
        .join(Evidence, Evidence.user_id == User.id, isouter=True)
        .filter(Evidence.deleted_at == None)
        .group_by(Department.id, Department.name, Department.code)
        .all()
    )
    return [{"name": r.name, "code": r.code, "evidence_count": r.count} for r in rows]


@router.get("/daily-hen-summary")
async def get_daily_hen_summary(db: Session = Depends(get_db)):
    """Return daily total hen counts grouped by date."""
    from app.database.models import HenCountSession
    sessions = db.query(HenCountSession).order_by(HenCountSession.created_at.desc()).all()
    day_map = {}
    for s in sessions:
        date_str = s.created_at.strftime("%Y-%m-%d")
        formatted = s.created_at.strftime("%d %b %Y")
        if date_str not in day_map:
            day_map[date_str] = {
                "date": date_str,
                "formatted_date": formatted,
                "total_hens": 0,
                "sessions_count": 0,
                "peak_visible": 0
            }
        day_map[date_str]["total_hens"] += (s.total_count or 0)
        day_map[date_str]["sessions_count"] += 1
        day_map[date_str]["peak_visible"] = max(day_map[date_str]["peak_visible"], s.visible_count or 0)
    return list(day_map.values())


@router.get("/daily-egg-summary")
async def get_daily_egg_summary(db: Session = Depends(get_db)):
    """Return daily total egg and tray counts grouped by date with deductions and timestamps."""
    from app.database.models import EggCountSession
    sessions = db.query(EggCountSession).order_by(EggCountSession.created_at.desc()).all()
    day_map = {}
    for s in sessions:
        date_str = s.created_at.strftime("%Y-%m-%d")
        formatted = s.created_at.strftime("%d %b %Y")
        if date_str not in day_map:
            day_map[date_str] = {
                "date": date_str,
                "formatted_date": formatted,
                "total_eggs": 0,
                "total_trays": 0,
                "expected_eggs": 0,
                "missing_eggs": 0,
                "sessions_count": 0,
                "recent_sessions": []
            }
        day_map[date_str]["total_eggs"] += (s.egg_count or 0)
        day_map[date_str]["total_trays"] += (s.tray_count or 0)
        day_map[date_str]["expected_eggs"] += (s.expected_egg_count or 0)
        day_map[date_str]["missing_eggs"] += (s.missing_egg_count or 0)
        day_map[date_str]["sessions_count"] += 1
        if len(day_map[date_str]["recent_sessions"]) < 10:
            day_map[date_str]["recent_sessions"].append({
                "id": s.id,
                "time": s.created_at.strftime("%I:%M:%S %p"),
                "tray_count": s.tray_count,
                "egg_count": s.egg_count,
                "missing_egg_count": s.missing_egg_count,
                "detection_mode": s.detection_mode,
                "source_type": s.source_type,
                "confidence": s.confidence,
                "notes": s.notes,
            })
    return list(day_map.values())


@router.get("/poultry-overview")
async def get_poultry_overview(db: Session = Depends(get_db)):
    """Consolidated poultry overview for Main Dashboard."""
    from app.database.models import EggCountSession, HenCountSession
    today = datetime.utcnow().date()
    today_str = today.strftime("%Y-%m-%d")

    egg_sessions = db.query(EggCountSession).order_by(EggCountSession.created_at.desc()).all()
    hen_sessions = db.query(HenCountSession).order_by(HenCountSession.created_at.desc()).all()

    today_egg_sessions = [s for s in egg_sessions if s.created_at.strftime("%Y-%m-%d") == today_str]
    today_hen_sessions = [s for s in hen_sessions if s.created_at.strftime("%Y-%m-%d") == today_str]

    return {
        "today": {
            "date": today.strftime("%d %b %Y"),
            "eggs": sum((s.egg_count or 0) for s in today_egg_sessions),
            "trays": sum((s.tray_count or 0) for s in today_egg_sessions),
            "missing_eggs": sum((s.missing_egg_count or 0) for s in today_egg_sessions),
            "egg_sessions": len(today_egg_sessions),
            "hens": sum((s.total_count or 0) for s in today_hen_sessions),
            "hen_sessions": len(today_hen_sessions),
        },
        "all_time": {
            "eggs": sum((s.egg_count or 0) for s in egg_sessions),
            "trays": sum((s.tray_count or 0) for s in egg_sessions),
            "missing_eggs": sum((s.missing_egg_count or 0) for s in egg_sessions),
            "hens": sum((s.total_count or 0) for s in hen_sessions),
        }
    }

