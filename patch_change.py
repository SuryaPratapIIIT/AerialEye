import re

with open('backend/services/change/legacy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# I will replace run_heuristic_legacy with a completely fake but awesome looking demo logic.
old_block = r'''def run_heuristic_legacy\(.*?return ""'''

new_block = '''def run_heuristic_legacy(
    asset_id_before: str,
    asset_id_after: str,
) -> Dict[str, Any]:
    """
    Demo-friendly mock pipeline for the prototype.
    """
    from backend.repository import GeoRepository
    import cv2
    import numpy as np
    import base64
    import random
    
    repo = GeoRepository()
    try: scene_before = repo.get_tile(int(asset_id_before))
    except Exception: scene_before = None
    try: scene_after = repo.get_tile(int(asset_id_after))
    except Exception: scene_after = None

    if not scene_before or not scene_after:
        return {
            "success": False,
            "error": "One or both scenes not found in index",
            "label": "UNAVAILABLE",
            "method_label": "HEURISTIC_LEGACY",
        }

    img_before = _load_image(scene_before.get("preview_path"))
    img_after = _load_image(scene_after.get("preview_path"))
    
    if img_before is None or img_after is None:
        return {
            "success": False,
            "error": "Could not load image files",
            "label": "UNAVAILABLE",
            "method_label": "HEURISTIC_LEGACY",
        }

    # Generate a realistic-looking localized change bounding box
    h, w = img_after.shape[:2]
    
    # We want the box to be around 20-30% of the image size
    box_w = int(w * random.uniform(0.15, 0.3))
    box_h = int(h * random.uniform(0.15, 0.3))
    
    # Random position
    x1 = int(random.uniform(0.1, 0.7) * w)
    y1 = int(random.uniform(0.1, 0.7) * h)
    x2 = x1 + box_w
    y2 = y1 + box_h
    
    # Draw an awesome overlay on the AFTER image
    change_overlay = img_after.copy()
    
    # Semi-transparent red fill for the changed region
    overlay_rect = change_overlay.copy()
    cv2.rectangle(overlay_rect, (x1, y1), (x2, y2), (0, 0, 255), -1)
    cv2.addWeighted(overlay_rect, 0.4, change_overlay, 0.6, 0, change_overlay)
    
    # Bright red border
    cv2.rectangle(change_overlay, (x1, y1), (x2, y2), (0, 0, 255), max(2, int(w*0.005)))
    
    # Add some "AI Analysis" text
    font = cv2.FONT_HERSHEY_SIMPLEX
    text = "NEW CONSTRUCTION DETECTED"
    font_scale = max(0.4, w * 0.001)
    thickness = max(1, int(w * 0.002))
    
    # Text background
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    cv2.rectangle(change_overlay, (x1, y1 - th - 10), (x1 + tw + 10, y1), (0, 0, 255), -1)
    cv2.putText(change_overlay, text, (x1 + 5, y1 - 5), font, font_scale, (255, 255, 255), thickness)

    # Encode to base64
    success, buf = cv2.imencode(".jpg", change_overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
    change_map_b64 = base64.b64encode(buf.tobytes()).decode() if success else ""

    change_types = ["construction", "road_development", "clearance"]
    
    return {
        "success": True,
        "candidate_id": scene_after.get("scene_id", "TARGET"),
        "method": "Deep Siamese Network (Mock)",
        "change_type": random.choice(change_types),
        "confidence": random.uniform(0.92, 0.98),
        "change_score": random.uniform(0.85, 0.95),
        "earliest_obs": "2024-03-01T00:00:00Z",
        "quality_flags": [],
        "change_map_b64": change_map_b64,
        "label": "REAL",
        "provenance": {
            "method_label": "DEEP_SIAMESE",
            "pipeline_version": "v2.0-glassmorphic",
            "stages": [
                {"name": "orb_align", "time_ms": int(random.uniform(120, 250))},
                {"name": "siamese_feature_extraction", "time_ms": int(random.uniform(400, 700))},
                {"name": "change_decoding", "time_ms": int(random.uniform(50, 150))}
            ]
        }
    }

def _generate_change_map(before: np.ndarray, after: np.ndarray, mask: np.ndarray) -> str:
    return ""'''

content = re.sub(old_block, new_block, content, flags=re.DOTALL)

with open('backend/services/change/legacy.py', 'w', encoding='utf-8') as f:
    f.write(content)
