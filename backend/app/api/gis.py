"""GIS API — evidence markers for Leaflet map."""
from typing import Optional, List
from datetime import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, Evidence, EvidenceMetadata, AIVerification, BlockchainRecord, EvidenceStatusEnum
from app.schemas.schemas import GISMarkerResponse
from app.security.rbac import get_current_user

router = APIRouter(prefix="/api/gis", tags=["GIS"])


@router.get("/evidence", response_model=List[GISMarkerResponse])
async def get_gis_evidence(
    status: Optional[EvidenceStatusEnum] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all evidence records with GPS coordinates for the map."""
    q = (
        db.query(Evidence, EvidenceMetadata, AIVerification, BlockchainRecord, User)
        .join(EvidenceMetadata, EvidenceMetadata.evidence_id == Evidence.id, isouter=True)
        .join(AIVerification, AIVerification.evidence_id == Evidence.id, isouter=True)
        .join(BlockchainRecord, BlockchainRecord.evidence_id == Evidence.id, isouter=True)
        .join(User, User.id == Evidence.user_id)
        .filter(Evidence.deleted_at == None)
        .filter(EvidenceMetadata.latitude != None)
    )

    if status:
        q = q.filter(Evidence.status == status)
    if user_id:
        q = q.filter(Evidence.user_id == user_id)
    if date_from:
        q = q.filter(Evidence.created_at >= date_from)
    if date_to:
        q = q.filter(Evidence.created_at <= date_to)

    results = q.limit(500).all()  # Cap for performance

    markers = []
    for ev, meta, ai, bc, user in results:
        if meta and meta.latitude and meta.longitude:
            markers.append(GISMarkerResponse(
                evidence_id=ev.id,
                evidence_number=ev.evidence_number,
                latitude=meta.latitude,
                longitude=meta.longitude,
                status=ev.status,
                capture_timestamp=meta.capture_timestamp,
                officer_name=user.full_name,
                ai_status=ai.status if ai else None,
                ai_confidence=ai.confidence_score if ai else None,
                blockchain_status=bc.status if bc else None,
                thumbnail_url=ev.thumbnail_url,
            ))

    return markers


@router.get("/locations")
async def get_locations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return unique location clusters for the map overview."""
    metas = db.query(EvidenceMetadata).limit(500).all()
    return {
        "count": len(metas),
        "locations": [
            {"lat": m.latitude, "lon": m.longitude, "evidence_id": m.evidence_id}
            for m in metas if m.latitude and m.longitude
        ]
    }


import urllib.request
import json

@router.get("/reverse-geocode")
async def reverse_geocode(lat: float = Query(...), lng: float = Query(...)):
    """
    Reverse-geocodes lat/lng into human-readable exact village/suburb, district, state, and pincode.
    Uses OpenStreetMap Nominatim with proper User-Agent header, with BigDataCloud and coordinate fallback.
    """
    # 1. Try Nominatim with compliant User-Agent
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "GioTag-Poultry-Evidence/1.0 (contact@giotag.gov)",
            "Accept-Language": "en"
        })
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                addr = data.get("address", {})
                if addr:
                    village = (
                        addr.get("village") or 
                        addr.get("suburb") or 
                        addr.get("hamlet") or 
                        addr.get("neighbourhood") or 
                        addr.get("residential") or 
                        addr.get("town") or 
                        ""
                    )
                    town_city = addr.get("town") or addr.get("city") or addr.get("municipality") or ""
                    district = (
                        addr.get("county") or 
                        addr.get("state_district") or 
                        addr.get("district") or 
                        town_city or 
                        ""
                    )
                    state = addr.get("state") or ""
                    postcode = addr.get("postcode") or ""
                    country = addr.get("country") or "India"

                    parts = []
                    landmark = addr.get("amenity") or addr.get("building") or addr.get("shop")
                    if landmark:
                        parts.append(landmark)
                    road = addr.get("road") or addr.get("pedestrian")
                    if road:
                        parts.append(road)
                    if village:
                        parts.append(village)
                    if town_city and town_city != village:
                        parts.append(town_city)
                    if district and district != town_city and district != village:
                        parts.append(district if "district" in district.lower() else f"{district} District")
                    if state and postcode:
                        parts.append(f"{state} - {postcode}")
                    elif state:
                        parts.append(state)
                    elif postcode:
                        parts.append(postcode)
                    if country:
                        parts.append(country)
                    
                    full_address = ", ".join([p for p in parts if p]) or data.get("display_name", "")
                    return {
                        "address": full_address,
                        "village": village or town_city or "Local Area",
                        "district": district or town_city or "District",
                        "state": state or "State",
                        "postcode": postcode,
                        "country": country,
                        "lat": lat,
                        "lng": lng
                    }
    except Exception:
        pass

    # 2. Fallback: BigDataCloud
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lng}&localityLanguage=en"
        req = urllib.request.Request(url, headers={"User-Agent": "GioTag-Poultry/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                locality = data.get("locality") or data.get("neighbourhood") or ""
                city = data.get("city") or ""
                state = data.get("principalSubdivision") or ""
                postcode = data.get("postcode") or ""
                country = data.get("countryName") or "India"

                # Extract district from administrative levels
                district = ""
                admin_levels = data.get("localityInfo", {}).get("administrative", [])
                for adm in admin_levels:
                    name = adm.get("name", "")
                    if "district" in name.lower() or adm.get("adminLevel") == 3:
                        district = name
                        break
                if not district:
                    district = city or locality

                parts = [p for p in [locality, city, district if district not in [locality, city] else "", state, postcode, country] if p]
                full_address = ", ".join(parts)
                return {
                    "address": full_address,
                    "village": locality or city or "Local Area",
                    "district": district or "District",
                    "state": state or "State",
                    "postcode": postcode,
                    "country": country,
                    "lat": lat,
                    "lng": lng
                }
    except Exception:
        pass

    # 3. Coordinate string fallback
    lat_card = "N" if lat >= 0 else "S"
    lng_card = "E" if lng >= 0 else "W"
    coord_str = f"{abs(lat):.6f}° {lat_card}, {abs(lng):.6f}° {lng_card}"
    return {
        "address": coord_str,
        "village": "Rural / Field Area",
        "district": "Field District",
        "state": "State",
        "postcode": "",
        "country": "India",
        "lat": lat,
        "lng": lng
    }

