import time
import math
import threading
import cv2
import numpy as np
import os
import torch

class OpticalHenTracker:
    def __init__(self, model_path=None):
        self.MODEL_PATH = model_path
        self.DEVICE = 0 if torch.cuda.is_available() else "cpu"
        
        from app.ai.shared_model import get_shared_model
        self.model = get_shared_model(model_path)
        
        self.state_lock = threading.RLock()
        self.reset_state()

    def reset_state(self):
        with self.state_lock:
            self.hens = {}
            self.next_hen_number = 1
            self.max_total_hens = 0
            self.latest_detections = []
            self.latest_frame_number = 0
            self.latest_video_time = 0.0
            self.total_inference_count = 0
            self.ai_fps = 30.0

    def process_live_frame(self, frame, frame_number=0, video_time=0.0):
        started = time.time()
        fh, fw = frame.shape[:2]

        with self.state_lock:
            self.latest_frame_number = frame_number
            self.latest_video_time = video_time
            self.total_inference_count += 1

            # 1. Direct high-speed YOLO inference on incoming live frame
            results = self.model.predict(
                source=frame,
                verbose=False,
                conf=0.035,
                iou=0.55,
                imgsz=640,
                device=self.DEVICE
            )

            raw_boxes = results[0].boxes.xyxy.cpu().numpy() if (results and len(results) > 0 and results[0].boxes is not None) else []
            raw_confs = results[0].boxes.conf.cpu().numpy() if (results and len(results) > 0 and results[0].boxes is not None) else []

            # 2. Balanced comb color mask: captures rich red, pale pink, and orange-red combs
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h_ch, s_ch, v_ch = cv2.split(hsv)
            b_ch, g_ch, r_ch = cv2.split(frame.astype(np.float32))
            comb_mask = (
                (((h_ch >= 125) | (h_ch <= 42)) & (s_ch > 4) & (v_ch > 10) & ((r_ch - g_ch) > -4)) |
                (((r_ch - np.maximum(g_ch, b_ch)) > -2) & (s_ch > 3) & (v_ch > 10)) |
                ((r_ch > 35) & (r_ch > g_ch - 5) & (r_ch > b_ch - 5))
            )

            scale_factor = max(fw, fh) / 640.0
            candidates = []
            for box, conf in zip(raw_boxes, raw_confs):
                x1, y1, x2, y2 = map(int, box)
                hw = x2 - x1
                hh = y2 - y1
                if hw < 3 or hh < 3 or hw > fw * 0.45 or hh > fh * 0.45:
                    continue

                aspect = hw / float(hh)
                if aspect < 0.12 or aspect > 5.0:
                    continue

                crop = comb_mask[max(0, y1):min(fh, y2), max(0, x1):min(fw, x2)]
                comb_px = np.count_nonzero(crop)

                # Color verification only for ultra-low-confidence proposals
                if comb_px < 1 and float(conf) < 0.05:
                    continue

                has_red = comb_px >= 1
                if has_red:
                    ys, xs = np.where(crop)
                    cx = x1 + float(np.median(xs if len(xs) > 0 else [hw / 2.0]))
                    cy = y1 + float(np.median(ys if len(ys) > 0 else [hh / 2.0]))
                    cw = float(np.percentile(xs, 95) - np.percentile(xs, 5)) if len(xs) > 1 else float(hw)
                    ch = float(np.percentile(ys, 95) - np.percentile(ys, 5)) if len(ys) > 1 else float(hh)
                    base_sz = max(12.0 * scale_factor, min(36.0 * scale_factor, max(cw, ch) + 4.0))
                else:
                    cx = (x1 + x2) / 2.0
                    cy = y1 + min(hh * 0.30, 16.0 * scale_factor)
                    base_sz = max(12.0 * scale_factor, min(34.0 * scale_factor, max(hw * 0.5, hh * 0.5)))

                hw_box = base_sz / 2.0
                hh_box = base_sz / 2.0
                box_final = [
                    max(0.0, float(cx - hw_box)),
                    max(0.0, float(cy - hh_box)),
                    min(float(fw - 1), float(cx + hw_box)),
                    min(float(fh - 1), float(cy + hh_box))
                ]

                candidates.append({
                    "box": box_final,
                    "center": (cx, cy),
                    "conf": float(conf)
                })

            # Deduplicate proposals on the exact same comb (radius 8px)
            candidates.sort(key=lambda d: d["conf"], reverse=True)
            dedup = []
            for d in candidates:
                c1 = d["center"]
                if not any(math.hypot(c1[0] - ex["center"][0], c1[1] - ex["center"][1]) < 8.0 for ex in dedup):
                    dedup.append(d)

            # 3. Match against active tracked hens
            matched_dets = set()
            used_hens = set()
            cands = []
            for d_idx, d in enumerate(dedup):
                dcx, dcy = d["center"]
                for hid, h in self.hens.items():
                    if h["lost"] > 15:
                        continue
                    hx, hy = h["center"]
                    dist = math.hypot(dcx - hx, dcy - hy)
                    if dist <= 45.0:
                        cands.append((dist, d_idx, hid))
            cands.sort(key=lambda x: x[0])

            for dist, d_idx, hid in cands:
                if d_idx in matched_dets or hid in used_hens:
                    continue
                matched_dets.add(d_idx)
                used_hens.add(hid)
                nb = dedup[d_idx]["box"]
                ob = self.hens[hid]["box"]
                # Smooth EMA box update
                self.hens[hid]["box"] = [0.55 * nb[i] + 0.45 * ob[i] for i in range(4)]
                self.hens[hid]["center"] = dedup[d_idx]["center"]
                self.hens[hid]["lost"] = 0
                self.hens[hid]["hits"] += 1
                self.hens[hid]["conf"] = dedup[d_idx]["conf"]

            for hid in self.hens:
                if hid not in used_hens:
                    self.hens[hid]["lost"] += 1

            # 4. Register new hens entering view
            for d_idx, d in enumerate(dedup):
                if d_idx in matched_dets:
                    continue
                dcx, dcy = d["center"]
                if not (2 <= dcx <= fw - 2 and 2 <= dcy <= fh - 2):
                    continue
                # Anti-duplicate: only register if not too close to active hen
                if any(math.hypot(dcx - h["center"][0], dcy - h["center"][1]) < 8.0 for h in self.hens.values() if h["lost"] <= 12):
                    continue

                hid = self.next_hen_number
                self.next_hen_number += 1
                self.hens[hid] = {
                    "box": d["box"],
                    "center": d["center"],
                    "lost": 0,
                    "hits": 1,
                    "conf": d["conf"]
                }

            # 5. Retire lost hens
            for hid in list(self.hens.keys()):
                b = self.hens[hid]["box"]
                cx, cy = self.hens[hid]["center"]
                exited = (cx < 2 or cx > fw - 2 or cy < 2 or cy > fh - 2 or
                          b[2] < 2 or b[0] > fw - 2 or b[3] < 2 or b[1] > fh - 2)
                if exited or self.hens[hid]["lost"] > 18:
                    del self.hens[hid]

            self.max_total_hens = max(self.max_total_hens, self.next_hen_number - 1)

            # 6. Build visible detections with sequential hen_numbers
            visible_hens = [hid for hid, h in self.hens.items() if h["lost"] <= 8 and h.get("hits", 0) >= 1]
            visible_hens.sort(key=lambda hid: hid)

            out_detections = []
            for hid in visible_hens:
                d = self.hens[hid]
                b = d["box"]
                x1 = int(max(0, min(fw - 1, b[0])))
                y1 = int(max(0, min(fh - 1, b[1])))
                x2 = int(max(0, min(fw - 1, b[2])))
                y2 = int(max(0, min(fh - 1, b[3])))
                if x2 - x1 < 2 or y2 - y1 < 2:
                    continue
                out_detections.append({
                    "hen_number": hid,
                    "box": [x1, y1, x2, y2],
                    "confidence": float(round(d.get("conf", 0.85), 2)),
                    "track_id": hid,
                    "predicted": False
                })

            out_detections.sort(key=lambda d: d["hen_number"])
            self.latest_detections = out_detections
            elapsed = time.time() - started
            fps = 1.0 / max(0.001, elapsed)

            return {
                "success": True,
                "busy": False,
                "video_time": video_time,
                "frame_width": fw,
                "frame_height": fh,
                "detections": out_detections,
                "total_hens": self.max_total_hens,
                "visible_hens": len(out_detections),
                "ai_frames": self.total_inference_count,
                "ai_fps": round(fps, 1)
            }
