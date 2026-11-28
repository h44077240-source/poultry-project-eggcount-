import logging
from typing import Optional

from app.ai.detector_interface import ImageDetector
from app.ai.yolo_service import detect_objects

logger = logging.getLogger(__name__)

class CustomYOLODetector(ImageDetector):
    """
    Egg & tray counter using local trained YOLO model.
    Implements the ImageDetector interface for drop-in replacement.
    """

    def analyze(self, image_bytes: bytes, mime_type: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Send the image to YOLO service and return a structured count result.
        """
        try:
            results = detect_objects(image_bytes, conf_threshold=0.20)
            
            tray_count = results.get("tray_count", 0)
            detected_eggs = results.get("egg_count", 0)
            expected_eggs = results.get("expected_egg_count", tray_count * 30)
            missing_eggs = results.get("missing_egg_count", 0)
            
            if target == "trays":
                egg_count = detected_eggs if (detected_eggs > 0 and detected_eggs != expected_eggs) else expected_eggs
            elif target == "eggs":
                egg_count = detected_eggs if detected_eggs > 0 else expected_eggs
            else:
                egg_count = 0

            conf_val = results.get("confidence", 0.0)
            if conf_val > 0.5:
                confidence_str = "high"
            elif conf_val > 0.15:
                confidence_str = "medium"
            else:
                confidence_str = "low"
                
            return {
                "success": True,
                "egg_count": egg_count,
                "tray_count": tray_count,
                "expected_egg_count": expected_eggs,
                "missing_egg_count": missing_eggs,
                "hen_count": results.get("hen_count", 0),
                "tray_types": {
                    "green_plastic": tray_count,
                    "paper_cardboard": 0,
                    "other": 0,
                    "unknown": 0
                },
                "confidence": confidence_str,
                "image_quality": "good",
                "notes": f"Detected {tray_count} egg tray(s) ({egg_count} eggs) using trained YOLO model."
            }
        except Exception as exc:
            logger.error("YOLO detection error: %s", exc, exc_info=True)
            raise

    def chat_analyze(self, message: str, image_bytes: Optional[bytes], mime_type: str = "image/jpeg") -> dict:
        """
        Conversational chat analysis using live farm database intelligence and YOLO counts.
        """
        try:
            from app.database.session import SessionLocal
            from app.ai.farm_chat_service import get_live_farm_data, rule_based_fallback_chat
            db = SessionLocal()
            try:
                farm_data = get_live_farm_data(db)
            finally:
                db.close()

            structured_analysis = None
            prefix = ""
            if image_bytes:
                structured_analysis = self.analyze(image_bytes, mime_type, target="trays")
                prefix = (
                    f"Visual Detection Summary from uploaded image:\n"
                    f"• Egg Trays: {structured_analysis.get('tray_count', 0)} trays\n"
                    f"• Eggs: {structured_analysis.get('egg_count', 0)} eggs\n"
                    f"• Hens: {structured_analysis.get('hen_count', 0)} birds\n\n"
                )
            
            data_reply = rule_based_fallback_chat(message, farm_data)
            return {"reply": prefix + data_reply, "analysis": structured_analysis}
        except Exception as exc:
            logger.error("YOLO chat_analyze fallback error: %s", exc)
            return {
                "reply": "Hello! I am your KR Poultry AI Assistant. Please ask any question about today's egg counts, tray counts, hen tracking, or suspicious uploads.",
                "analysis": None
            }
            
    def analyze_dual(self, top_image_bytes: bytes, side_image_bytes: bytes, mime_type_top: str = "image/jpeg", mime_type_side: str = "image/jpeg", target: str = "trays") -> dict:
        """
        Analyze dual images (top view and side view) using the dedicated egg tray YOLO model.
        Ported from Egg_Inventory_Project (egg_app.py).
        """
        try:
            from app.ai.egg_tray_service import analyze_dual_egg_trays
            return analyze_dual_egg_trays(top_image_bytes, side_image_bytes)
        except Exception as exc:
            logger.error("YOLO dual detection error: %s", exc, exc_info=True)
            # Fallback to generic detect_objects if dedicated dual pipeline encounters unexpected error
            try:
                top_results = detect_objects(top_image_bytes, conf_threshold=0.20)
                side_results = detect_objects(side_image_bytes, conf_threshold=0.20)
                top_trays = top_results.get("tray_count", 0)
                side_trays = side_results.get("tray_count", 0)
                tray_count = (top_trays * side_trays) if (top_trays > 0 and side_trays > 0) else max(top_trays, side_trays)
                egg_count = tray_count * 30
                return {
                    "success": True,
                    "egg_count": egg_count,
                    "tray_count": tray_count,
                    "expected_egg_count": egg_count,
                    "missing_egg_count": 0,
                    "hen_count": 0,
                    "tray_types": {"green_plastic": tray_count, "paper_cardboard": 0, "other": 0, "unknown": 0},
                    "confidence": "medium",
                    "image_quality": "fair",
                    "notes": f"Fallback dual analysis: Top view {top_trays} stack(s), Side view {side_trays} layer(s). Total: {tray_count} trays ({egg_count} eggs)."
                }
            except Exception:
                raise exc
