"""
Farm Chat Intelligence Service for KR Group Poultry.
Equips the AI Vision Chat assistant with real-time database knowledge:
- Today's and historical egg and tray counts (with deductions)
- Today's and historical hen flock counts (from Hen Comb Tracking)
- Evidence verification audit: who uploaded suspicious vs verified images
- Date-wise queries (e.g. "27 Nov count", "yesterday", "today")
- Warm, friendly, conversational tone (Tanglish / Tamil / English)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.models import (
    EggCountSession,
    HenCountSession,
    Evidence,
    EvidenceStatusEnum,
    User,
    AIVerification
)

logger = logging.getLogger(__name__)


def get_live_farm_data(db: Session) -> Dict[str, Any]:
    """Extract real-time poultry, egg, hen, and evidence data from the database."""
    now_utc = datetime.utcnow()
    # IST is UTC + 5:30
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    today_str = now_utc.strftime("%Y-%m-%d")
    today_ist_str = now_ist.strftime("%Y-%m-%d")

    # ── 1. Egg Count Sessions & Daily Aggregates ──────────────────────────────
    egg_sessions: List[EggCountSession] = (
        db.query(EggCountSession)
        .order_by(EggCountSession.created_at.desc())
        .all()
    )

    today_eggs = 0
    today_trays = 0
    today_missing = 0
    today_egg_batches = 0
    total_eggs_all_time = 0
    total_trays_all_time = 0

    egg_by_date: Dict[str, Dict[str, Any]] = {}
    for s in egg_sessions:
        if not s.created_at:
            continue
        s_date_str = s.created_at.strftime("%Y-%m-%d")
        s_formatted = s.created_at.strftime("%d %b %Y")

        if s_date_str not in egg_by_date:
            egg_by_date[s_date_str] = {
                "date": s_date_str,
                "formatted": s_formatted,
                "total_eggs": 0,
                "total_trays": 0,
                "missing_eggs": 0,
                "expected_eggs": 0,
                "batches": 0,
                "recent_sessions": []
            }

        egg_by_date[s_date_str]["total_eggs"] += (s.egg_count or 0)
        egg_by_date[s_date_str]["total_trays"] += (s.tray_count or 0)
        egg_by_date[s_date_str]["missing_eggs"] += (s.missing_egg_count or 0)
        egg_by_date[s_date_str]["expected_eggs"] += (s.expected_egg_count or 0)
        egg_by_date[s_date_str]["batches"] += 1
        if len(egg_by_date[s_date_str]["recent_sessions"]) < 5:
            egg_by_date[s_date_str]["recent_sessions"].append({
                "time": s.created_at.strftime("%I:%M %p"),
                "trays": s.tray_count,
                "eggs": s.egg_count,
                "missing": s.missing_egg_count,
                "mode": s.detection_mode
            })

        total_eggs_all_time += (s.egg_count or 0)
        total_trays_all_time += (s.tray_count or 0)

        # Count for today (either UTC or IST)
        if s_date_str in (today_str, today_ist_str):
            today_eggs += (s.egg_count or 0)
            today_trays += (s.tray_count or 0)
            today_missing += (s.missing_egg_count or 0)
            today_egg_batches += 1

    # ── 2. Hen Tracking Sessions & Daily Aggregates ───────────────────────────
    hen_sessions: List[HenCountSession] = (
        db.query(HenCountSession)
        .order_by(HenCountSession.created_at.desc())
        .all()
    )

    today_hens = 0
    today_hen_sessions = 0
    total_hens_all_time = 0

    hen_by_date: Dict[str, Dict[str, Any]] = {}
    for hs in hen_sessions:
        if not hs.created_at:
            continue
        hs_date_str = hs.created_at.strftime("%Y-%m-%d")
        hs_formatted = hs.created_at.strftime("%d %b %Y")

        if hs_date_str not in hen_by_date:
            hen_by_date[hs_date_str] = {
                "date": hs_date_str,
                "formatted": hs_formatted,
                "total_hens": 0,
                "sessions_count": 0,
                "recent_sessions": []
            }

        hen_by_date[hs_date_str]["total_hens"] += (hs.total_count or 0)
        hen_by_date[hs_date_str]["sessions_count"] += 1
        if len(hen_by_date[hs_date_str]["recent_sessions"]) < 5:
            hen_by_date[hs_date_str]["recent_sessions"].append({
                "time": hs.created_at.strftime("%I:%M %p"),
                "count": hs.total_count,
                "visible": hs.visible_count,
                "source": hs.source_type,
                "video": hs.video_filename
            })

        total_hens_all_time += (hs.total_count or 0)
        if hs_date_str in (today_str, today_ist_str):
            today_hens += (hs.total_count or 0)
            today_hen_sessions += 1

    # ── 3. Evidence Verification Audit (Who uploaded what) ────────────────────
    ev_all = db.query(Evidence).filter(Evidence.deleted_at == None).all()
    total_evidence = len(ev_all)
    verified_evidence = sum(1 for e in ev_all if e.status == EvidenceStatusEnum.VERIFIED)
    suspicious_evidence = sum(1 for e in ev_all if e.status == EvidenceStatusEnum.SUSPICIOUS)
    pending_evidence = sum(1 for e in ev_all if e.status in (EvidenceStatusEnum.PENDING_SYNC, EvidenceStatusEnum.UPLOADED, EvidenceStatusEnum.REVIEW_REQUIRED))
    rejected_evidence = sum(1 for e in ev_all if e.status == EvidenceStatusEnum.REJECTED)

    # Detailed Suspicious List: who uploaded them
    suspicious_items = []
    suspicious_records = (
        db.query(Evidence, User)
        .join(User, Evidence.user_id == User.id)
        .filter(Evidence.status == EvidenceStatusEnum.SUSPICIOUS, Evidence.deleted_at == None)
        .order_by(Evidence.created_at.desc())
        .limit(20)
        .all()
    )
    for ev, u in suspicious_records:
        suspicious_items.append({
            "evidence_number": ev.evidence_number,
            "uploaded_by": u.full_name,
            "user_email": u.email,
            "user_role": u.role.value if hasattr(u.role, 'value') else str(u.role),
            "filename": ev.image_filename,
            "date": ev.created_at.strftime("%d %b %Y, %I:%M %p") if ev.created_at else "Unknown",
            "reason": ev.rejection_reason or ev.notes or "AI anomaly detected (possible tamper or spoof)"
        })

    # Verified Evidence grouped by user
    user_verified_map: Dict[str, int] = {}
    verified_records = (
        db.query(User.full_name, func.count(Evidence.id))
        .join(Evidence, Evidence.user_id == User.id)
        .filter(Evidence.status == EvidenceStatusEnum.VERIFIED, Evidence.deleted_at == None)
        .group_by(User.full_name)
        .all()
    )
    for name, cnt in verified_records:
        user_verified_map[name] = cnt

    # All registered active officers/users
    users_list = []
    users = db.query(User).filter(User.deleted_at == None).all()
    for u in users:
        users_list.append({
            "name": u.full_name,
            "role": u.role.value if hasattr(u.role, 'value') else str(u.role),
            "email": u.email,
            "active": u.is_active
        })

    return {
        "today_ist": now_ist.strftime("%d %B %Y (%A)"),
        "today_eggs": today_eggs,
        "today_trays": today_trays,
        "today_missing": today_missing,
        "today_egg_batches": today_egg_batches,
        "total_eggs_all_time": total_eggs_all_time,
        "total_trays_all_time": total_trays_all_time,
        "egg_by_date": egg_by_date,
        "today_hens": today_hens,
        "today_hen_sessions": today_hen_sessions,
        "total_hens_all_time": total_hens_all_time,
        "hen_by_date": hen_by_date,
        "total_evidence": total_evidence,
        "verified_evidence": verified_evidence,
        "suspicious_evidence": suspicious_evidence,
        "pending_evidence": pending_evidence,
        "rejected_evidence": rejected_evidence,
        "suspicious_items": suspicious_items,
        "user_verified_map": user_verified_map,
        "users_list": users_list,
    }


def build_system_context_prompt(data: Dict[str, Any]) -> str:
    """Create a rich, structured prompt containing all current live data."""
    # Format date-wise egg rows
    egg_rows = []
    for d, info in sorted(data["egg_by_date"].items(), reverse=True)[:10]:
        egg_rows.append(
            f"- **{info['formatted']}**: {info['total_eggs']:,} eggs ({info['total_trays']} trays), "
            f"Deductions (missing): {info['missing_eggs']}, Batches: {info['batches']}"
        )
    egg_summary_str = "\n".join(egg_rows) if egg_rows else "- No egg sessions recorded yet."

    # Format date-wise hen rows
    hen_rows = []
    for d, info in sorted(data["hen_by_date"].items(), reverse=True)[:10]:
        hen_rows.append(
            f"- **{info['formatted']}**: {info['total_hens']:,} hens tagged across {info['sessions_count']} tracking sessions"
        )
    hen_summary_str = "\n".join(hen_rows) if hen_rows else "- No hen tracking sessions recorded yet."

    # Format suspicious uploads
    suspicious_rows = []
    for s in data["suspicious_items"][:10]:
        suspicious_rows.append(
            f"- **Officer {s['uploaded_by']}** ({s['user_role']}): File `{s['filename']}` on {s['date']} — Flagged: {s['reason']}"
        )
    suspicious_str = "\n".join(suspicious_rows) if suspicious_rows else "- None (All evidence files are clean or verified!)."

    # Format verified officers
    verified_rows = []
    for name, cnt in data["user_verified_map"].items():
        verified_rows.append(f"- **{name}**: {cnt} verified uploads")
    verified_str = "\n".join(verified_rows) if verified_rows else "- No verified uploads yet."

    return (
        "You are 'KR Poultry AI Assistant' — the friendly, expert farm intelligence and evidence verification companion "
        "for the KR Group Poultry Farm management system.\n\n"
        "### YOUR PERSONALITY & TONE:\n"
        "- Speak in clear, professional, friendly, and helpful English at all times.\n"
        "- If the user asks in English or Tanglish/Tamil, understand their intent perfectly and provide the response in clean, fluent English.\n"
        "- Be transparent, warm, professional, and 100% accurate with numbers.\n\n"
        "### CURRENT LIVE DATABASE RECORDS (USE THESE EXACT NUMBERS):\n"
        f"• **Current Date**: {data['today_ist']}\n"
        f"• **Today's Egg Count**: {data['today_eggs']:,} eggs ({data['today_trays']} trays) | Missing (Deductions): {data['today_missing']} | Batches scanned: {data['today_egg_batches']}\n"
        f"• **Today's Hen Count**: {data['today_hens']:,} hens identified & tagged ({data['today_hen_sessions']} video tracking runs)\n"
        f"• **All-Time Egg Total**: {data['total_eggs_all_time']:,} eggs ({data['total_trays_all_time']} trays)\n"
        f"• **All-Time Hen Tracking Total**: {data['total_hens_all_time']:,} hens counted\n"
        f"• **Evidence Summary**: Total: {data['total_evidence']} | Verified: {data['verified_evidence']} | Suspicious: {data['suspicious_evidence']} | Pending: {data['pending_evidence']}\n\n"
        "#### DATE-WISE EGG & TRAY BREAKDOWN:\n"
        f"{egg_summary_str}\n\n"
        "#### DATE-WISE HEN TRACKING BREAKDOWN:\n"
        f"{hen_summary_str}\n\n"
        "#### SUSPICIOUS EVIDENCE (WHO UPLOADED WHAT):\n"
        f"{suspicious_str}\n\n"
        "#### VERIFIED EVIDENCE BY OFFICER:\n"
        f"{verified_str}\n\n"
        "### INSTRUCTIONS FOR ANSWERING:\n"
        "1. Always reply in clear, friendly English.\n"
        "2. When the user asks about today's counts (egg, tray, hen), quote the exact numbers above.\n"
        "3. When the user asks who uploaded suspicious or verified images, name the specific officers and files from the records above.\n"
        "4. When the user asks about a specific date (e.g. '27 Nov', 'yesterday', or any day), look up that exact date above and report the egg count, trays, deductions, and hen count in English.\n"
        "5. If an image is provided, analyze the visual contents (egg count, tray count, hen count) and answer the user's query.\n"
        "6. Keep the conversation engaging, polite, helpful, and friendly like a true team partner!"
    )


def rule_based_fallback_chat(message: str, data: Dict[str, Any]) -> str:
    """
    Intelligent conversational fallback responder.
    Provides 100% accurate, friendly answers in English from live database facts
    even if the external cloud LLM is offline, unconfigured, or rate-limited.
    """
    msg = message.lower().strip()

    # ── 1. Suspicious Evidence Query ─────────────────────────────────────────
    if any(k in msg for k in ("suspicious", "susuplise", "sus", "anomal", "fake", "tamper", "fraud", "flagged")):
        if data["suspicious_evidence"] == 0:
            return (
                "Great news! Currently, there are **no suspicious evidence records** in the system (0 suspicious). "
                f"Out of {data['total_evidence']} total evidence files, **{data['verified_evidence']} files have been successfully verified** by our inspection officers. "
                "All evidence records are clean and verified! 👍"
            )
        items_str = ""
        for i, item in enumerate(data["suspicious_items"][:5], 1):
            items_str += f"\n{i}. **Officer {item['uploaded_by']}** ({item['user_role']})\n   • File: `{item['filename']}`\n   • Date: {item['date']}\n   • Flag Reason: {item['reason']}\n"
        return (
            f"Here is the suspicious evidence audit from our database:\nTotal Flagged: **{data['suspicious_evidence']} suspicious evidence files**.\n\n"
            f"**Flagged Upload Details & Officers:**{items_str}\n"
            f"**Total System Evidence:** {data['total_evidence']} | Verified: {data['verified_evidence']} | Pending: {data['pending_evidence']}.\n"
            "Please let me know if you would like detailed audit logs for any specific evidence ID!"
        )

    # ── 2. Who Uploaded / Verified Evidence Query ─────────────────────────────
    if (("who" in msg or "yaru" in msg or "yar" in msg) and ("upload" in msg or "verified" in msg or "image" in msg)) or ("officer" in msg and "upload" in msg):
        verified_lines = ""
        for name, cnt in data["user_verified_map"].items():
            verified_lines += f"\n• **{name}**: {cnt} verified evidence files"
        if not verified_lines:
            verified_lines = "\n• Currently no verified evidence recorded."
        
        susp_summary = ""
        if data["suspicious_items"]:
            susp_summary = f"\n\n⚠️ **Suspicious Uploads Flagged:**\n"
            for s in data["suspicious_items"][:4]:
                susp_summary += f"• **Officer {s['uploaded_by']}** — `{s['filename']}` ({s['date']})\n"

        return (
            f"Here is the evidence upload and verification summary by officer:\n\n"
            f"✅ **Verified Uploads by Officer:**{verified_lines}{susp_summary}\n\n"
            f"**Total System Evidence:** **{data['total_evidence']}** "
            f"({data['verified_evidence']} verified, {data['suspicious_evidence']} suspicious, {data['pending_evidence']} pending)."
        )

    # ── 3. Date-Specific Query (e.g. "27 Nov", "yesterday", "28", etc.) ─────
    for date_key, info in data["egg_by_date"].items():
        day_num = info["formatted"].split()[0]  # e.g. "27"
        month_name = info["formatted"].split()[1].lower()  # e.g. "nov"
        # Check if user mentioned this date
        if (day_num in msg and month_name in msg) or date_key in msg:
            hen_info = data["hen_by_date"].get(date_key, {"total_hens": 0, "sessions_count": 0})
            return (
                f"Here are the farm records for **{info['formatted']}**:\n\n"
                f"🥚 **Egg & Tray Inventory:**\n"
                f"• Verified Total Eggs: **{info['total_eggs']:,} eggs**\n"
                f"• Total Trays: **{info['total_trays']} trays**\n"
                f"• Deductions (Missing Eggs): **{info['missing_eggs']} eggs**\n"
                f"• Batches Scanned: **{info['batches']} sessions**\n\n"
                f"🐔 **Hen Tracking:**\n"
                f"• Total Hens Identified: **{hen_info['total_hens']:,} hens**\n"
                f"• Tracking Sessions: **{hen_info['sessions_count']} sessions**\n\n"
                "All records are saved securely in the database. Feel free to ask about any other date!"
            )

    # Yesterday query
    if "yesterday" in msg or "nethu" in msg:
        yesterday_utc = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        if yesterday_utc in data["egg_by_date"]:
            info = data["egg_by_date"][yesterday_utc]
            hen_info = data["hen_by_date"].get(yesterday_utc, {"total_hens": 0, "sessions_count": 0})
            return (
                f"Here is the farm report for **Yesterday ({info['formatted']})**:\n\n"
                f"🥚 **Eggs & Trays:** **{info['total_eggs']:,} eggs** ({info['total_trays']} trays)\n"
                f"⚠️ **Deductions:** {info['missing_eggs']} missing eggs\n"
                f"🐔 **Hens:** **{hen_info['total_hens']:,} hens** ({hen_info['sessions_count']} tracking sessions)\n\n"
                "All yesterday's batch and tracking data are logged in the database!"
            )
        else:
            return (
                "No egg or hen count sessions were recorded yesterday in the database. "
                "You can specify a date to check previous records (for example, '27 Nov report')!"
            )

    # ── 4. Egg & Tray Count (Today / General) ──────────────────────────────────
    if any(k in msg for k in ("egg", "tray", "muttai")) and any(k in msg for k in ("count", "evolo", "evlo", "total", "today", "inniku", "how many", "status", "inventory", "stock")):
        return (
            f"Here is the live egg inventory report for **Today ({data['today_ist']})**:\n\n"
            f"🥚 **Today's Verified Eggs:** **{data['today_eggs']:,} eggs**\n"
            f"📦 **Today's Total Trays:** **{data['today_trays']} trays**\n"
            f"⚠️ **Deductions (Missing Eggs):** **{data['today_missing']} eggs**\n"
            f"🔍 **Batches Scanned:** {data['today_egg_batches']} sessions\n\n"
            f"📊 **All-Time Egg Inventory:** **{data['total_eggs_all_time']:,} eggs** ({data['total_trays_all_time']} trays).\n"
            "Please let me know if you would like data for a specific date or batch!"
        )

    # ── 5. Hen & Flock Count (Today / General) ─────────────────────────────────
    if any(k in msg for k in ("hen", "koli", "kozhi", "flock", "comb")) and any(k in msg for k in ("count", "evolo", "evlo", "total", "today", "inniku", "how many", "status")):
        return (
            f"Here is the live hen tracking report for **Today ({data['today_ist']})**:\n\n"
            f"🐔 **Today's Unique Hens Tagged:** **{data['today_hens']:,} hens**\n"
            f"📹 **Video Tracking Sessions:** {data['today_hen_sessions']} runs\n"
            f"🏆 **All-Time Hens Counted:** **{data['total_hens_all_time']:,} hens**\n\n"
            "The sequence tracking model tagged each unique hen and logged it directly to the dashboard!"
        )

    # ── 6. Full Executive Report / All Data ────────────────────────────────────
    if any(w in msg for w in ("report", "elareportum", "all", "summary", "overview", "dashboard", "status")):
        return (
            f"Here is the complete **KR Group Poultry Farm Executive Summary**:\n\n"
            f"📅 **Date:** {data['today_ist']}\n\n"
            f"🥚 **EGG INVENTORY:**\n"
            f"• Today's Verified Eggs: **{data['today_eggs']:,} eggs** ({data['today_trays']} trays)\n"
            f"• Today's Missing (Deductions): **{data['today_missing']} eggs**\n"
            f"• Total Scanned Eggs (All-Time): **{data['total_eggs_all_time']:,} eggs**\n\n"
            f"🐔 **HEN TRACKING:**\n"
            f"• Today's Unique Hens: **{data['today_hens']:,} hens**\n"
            f"• Total Hens Tracked (All-Time): **{data['total_hens_all_time']:,} hens**\n\n"
            f"🛡️ **SECURITY & EVIDENCE AUDIT:**\n"
            f"• Total Uploaded Evidence: **{data['total_evidence']}**\n"
            f"• Verified Evidence: **{data['verified_evidence']}**\n"
            f"• Suspicious Evidence: **{data['suspicious_evidence']}**\n"
            f"• Pending Verification: **{data['pending_evidence']}**\n\n"
            "You can ask me about any specific date, batch, or officer upload at any time!"
        )

    # ── 7. Greetings / Default Warm Response ──────────────────────────────────
    return (
        f"Hello! 👋 I am your KR Poultry Farm AI Assistant.\n\n"
        f"Here is the current live summary for **Today ({data['today_ist']})**:\n"
        f"• 🥚 **Today's Eggs:** **{data['today_eggs']:,} eggs** ({data['today_trays']} trays)\n"
        f"• 🐔 **Today's Hens:** **{data['today_hens']:,} hens**\n"
        f"• 🛡️ **Evidence Status:** **{data['verified_evidence']} verified** / **{data['suspicious_evidence']} suspicious**\n\n"
        "Feel free to ask me any question about daily egg counts, hen flock tracking, suspicious uploads, or date-wise records. "
        "You can also upload an image for real-time visual analysis!"
    )


async def handle_farm_chat_query(
    db: Session,
    message: str,
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg"
) -> Dict[str, Any]:
    """
    Main entry point for AI Vision Chat.
    Attempts cloud LLM analysis (OpenAI / Gemini) with full database context;
    gracefully falls back to high-fidelity rule-based response on rate limit or missing key.
    """
    farm_data = get_live_farm_data(db)
    system_prompt = build_system_context_prompt(farm_data)

    reply_text: Optional[str] = None
    structured_analysis = None

    # Try OpenAI Vision first if key exists
    try:
        from app.config import settings
        if settings.OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            model_name = settings.OPENAI_MODEL or "gpt-4o"

            content_payload: list = []
            if image_bytes:
                import base64
                b64 = base64.b64encode(image_bytes).decode("utf-8")
                content_payload.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}", "detail": "high"}
                })
            content_payload.append({"type": "text", "text": message})

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_payload}
                ],
                temperature=0.3,
                max_tokens=800
            )
            reply_text = response.choices[0].message.content.strip()

            # If image was sent, also get structured counts
            if image_bytes:
                try:
                    from app.ai.openai_vision import OpenAIVisionDetector
                    detector = OpenAIVisionDetector()
                    structured_analysis = detector.analyze(image_bytes, mime_type)
                except Exception as e:
                    logger.warning("Image count analysis during chat: %s", e)
    except Exception as exc:
        logger.warning("Cloud LLM chat unavailable, using intelligent local data responder: %s", exc)

    # If cloud LLM failed or wasn't configured, use intelligent data-driven responder
    if not reply_text:
        # If an image was attached and local YOLO can count it:
        if image_bytes:
            try:
                from app.ai.yolo_detector import CustomYOLODetector
                yolo = CustomYOLODetector()
                structured_analysis = yolo.analyze(image_bytes, mime_type, target="trays")
                img_reply = (
                    f"Visual Detection Summary from uploaded image:\n"
                    f"• 📦 Egg Trays: **{structured_analysis.get('tray_count', 0)} trays**\n"
                    f"• 🥚 Eggs: **{structured_analysis.get('egg_count', 0)} eggs**\n"
                    f"• 🐔 Hens: **{structured_analysis.get('hen_count', 0)} hens**\n\n"
                )
                data_reply = rule_based_fallback_chat(message, farm_data)
                reply_text = img_reply + data_reply
            except Exception as e:
                logger.error("Local YOLO chat fallback error: %s", e)
                reply_text = rule_based_fallback_chat(message, farm_data)
        else:
            reply_text = rule_based_fallback_chat(message, farm_data)

    return {
        "reply": reply_text,
        "analysis": structured_analysis
    }
