import base64
import json
import logging
import os
import threading
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.services.vision_engine import (
    AnalysisResult,
    VisionEngineError,
    _build_transformed_payload,
    _normalize_category_name,
    default_response_schema,
    validate_response_schema,
)

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_YOLO_MODEL_PATH = ROOT_DIR / "spatial_asset_yolo11n_best.pt"
YOLO_MODEL_PATH_ENV = "YOLO_MODEL_PATH"
YOLO_CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.25"))
YOLO_IOU_THRESHOLD = float(os.getenv("YOLO_IOU_THRESHOLD", "0.45"))

CLASS_TO_CATEGORY = {
    "buildings": "Properties & Buildings",
    "building": "Properties & Buildings",
    "trees": "Trees & Green Cover",
    "tree": "Trees & Green Cover",
    "parks_open_spaces": "Parks & Open Spaces",
    "parks": "Parks & Open Spaces",
    "park": "Parks & Open Spaces",
    "open_spaces": "Parks & Open Spaces",
    "water": "Water Bodies",
    "water_bodies": "Water Bodies",
}

_MODEL_CACHE: Dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


def _resolve_model_path(explicit_path: Optional[str] = None) -> Path:
    configured = explicit_path or os.getenv(YOLO_MODEL_PATH_ENV, "")
    if configured.strip():
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path.resolve()
    return DEFAULT_YOLO_MODEL_PATH.resolve()


def _load_model(model_path: Path) -> Any:
    if not model_path.exists() or not model_path.is_file():
        raise VisionEngineError(
            f"YOLO model file not found at: {model_path}. Set {YOLO_MODEL_PATH_ENV} if needed."
        )

    cache_key = str(model_path)
    with _MODEL_LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]

        try:
            from ultralytics import YOLO
        except Exception as err:
            raise VisionEngineError(
                "Ultralytics is not installed. Run `pip install -r requirements.txt` before using Naming Analysis."
            ) from err

        logger.info("Loading YOLO model from %s", model_path)
        model = YOLO(str(model_path))
        _MODEL_CACHE[cache_key] = model
        return model


def _clamp_percent(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 100.0:
        return 100.0
    return value


def _map_class_name_to_category(raw_class_name: str) -> str:
    normalized = raw_class_name.strip().lower().replace("-", "_").replace(" ", "_")
    mapped = CLASS_TO_CATEGORY.get(normalized)
    if mapped:
        return mapped
    return _normalize_category_name(raw_class_name.replace("_", " "))


def _build_asset(
    class_name: str,
    confidence: float,
    xyxy: List[float],
    image_width: int,
    image_height: int,
    index: int,
) -> Dict[str, Any]:
    x_min = _clamp_percent((xyxy[0] / image_width) * 100.0)
    y_min = _clamp_percent((xyxy[1] / image_height) * 100.0)
    x_max = _clamp_percent((xyxy[2] / image_width) * 100.0)
    y_max = _clamp_percent((xyxy[3] / image_height) * 100.0)

    if x_max < x_min:
        x_min, x_max = x_max, x_min
    if y_max < y_min:
        y_min, y_max = y_max, y_min

    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0

    box_width_pct = max(x_max - x_min, 0.0)
    box_height_pct = max(y_max - y_min, 0.0)
    coverage_percent = (box_width_pct * box_height_pct) / 100.0

    # Area and dimensions are approximate because pixel detections do not include scale metadata.
    estimated_area_sq_m = round(coverage_percent * 10.0, 2)
    est_length = round((box_width_pct / 100.0) * 100.0, 2)
    est_width = round((box_height_pct / 100.0) * 100.0, 2)

    category = _map_class_name_to_category(class_name)
    readable_subcategory = class_name.strip() or "unknown"

    return {
        "unique_id": f"naming_asset_{index}",
        "category": category,
        "subcategory": readable_subcategory,
        "confidence_percent": round(_clamp_percent(confidence * 100.0), 2),
        "estimated_count": 1,
        "estimated_area_sq_m": estimated_area_sq_m,
        "estimated_dimensions_m": {
            "length": est_length,
            "width": est_width,
        },
        "estimated_coverage_percent": round(coverage_percent, 4),
        "condition_status": "Monitored",
        "maintenance_priority": "Medium",
        "center_coordinates": {
            "x": round(center_x, 4),
            "y": round(center_y, 4),
        },
        "bounding_box": {
            "x_min": round(x_min, 4),
            "y_min": round(y_min, 4),
            "x_max": round(x_max, 4),
            "y_max": round(y_max, 4),
        },
        "polygon_coordinates": [
            {"x": round(x_min, 4), "y": round(y_min, 4)},
            {"x": round(x_max, 4), "y": round(y_min, 4)},
            {"x": round(x_max, 4), "y": round(y_max, 4)},
            {"x": round(x_min, 4), "y": round(y_max, 4)},
        ],
        "visual_description": f"{readable_subcategory} detected by YOLO naming model.",
        "estimation_basis": "Bounding box predicted by YOLO model and normalized to 0-100 image coordinates.",
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _build_schema_payload(
    assets: List[Dict[str, Any]],
    model_name: str,
    image_width: int,
    image_height: int,
) -> Dict[str, Any]:
    payload = default_response_schema()
    payload["detected_assets"] = assets

    category_stats = payload["category_statistics"]
    for asset in assets:
        category = str(asset.get("category", "")).strip()
        if category not in category_stats:
            category_stats[category] = {"count": 0, "total_area_sq_m": 0.0, "coverage_percent": 0.0}

        category_stats[category]["count"] += max(_to_int(asset.get("estimated_count"), 1), 0)
        category_stats[category]["total_area_sq_m"] += max(_to_float(asset.get("estimated_area_sq_m"), 0.0), 0.0)
        category_stats[category]["coverage_percent"] += _clamp_percent(
            _to_float(asset.get("estimated_coverage_percent"), 0.0)
        )

    for category, stats in category_stats.items():
        stats["count"] = max(_to_int(stats.get("count"), 0), 0)
        stats["total_area_sq_m"] = round(max(_to_float(stats.get("total_area_sq_m"), 0.0), 0.0), 2)
        stats["coverage_percent"] = round(_clamp_percent(_to_float(stats.get("coverage_percent"), 0.0)), 4)
        category_stats[category] = stats

    mean_confidence = 0.0
    if assets:
        mean_confidence = sum(_to_float(asset.get("confidence_percent"), 0.0) for asset in assets) / len(assets)

    payload["image_analysis"] = {
        "scene_type": "YOLO Spatial Asset Detection",
        "image_quality": "Processed",
        "estimated_total_area_sq_m": round(sum(
            _to_float(asset.get("estimated_area_sq_m"), 0.0) for asset in assets
        ), 2),
        "overall_detection_confidence_percent": round(_clamp_percent(mean_confidence), 2),
        "dominant_land_use": "Mixed Urban",
    }

    payload["ai_insights"] = [
        f"Naming Analysis used YOLO model {model_name} on image resolution {image_width}x{image_height}.",
        f"Detected {len(assets)} asset candidates across mapped categories.",
        "Coordinates and overlays are synchronized to normalized 0-100 space for frontend/GIS rendering.",
    ]

    return payload


def _build_visualization_data_url_from_saved_frame(result_obj: Any) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_path = Path(temp_file.name)

        try:
            # Save using Ultralytics renderer directly (no intermediate image conversion).
            result_obj.save(filename=str(temp_path))
            if not temp_path.exists() or not temp_path.is_file():
                return None
            data = temp_path.read_bytes()
            if not data:
                return None
            encoded = base64.b64encode(data).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as err:
        logger.warning("Unable to build naming visualization image from saved frame: %s", err)
        return None


def _build_visualization_data_url(result_obj: Any) -> str:
    data_url = _build_visualization_data_url_from_saved_frame(result_obj)
    if not data_url:
        raise VisionEngineError(
            "Failed to generate YOLO rendered frame for Naming Analysis."
        )
    return data_url


def analyze_naming_image(image_path: str, model_path: Optional[str] = None) -> AnalysisResult:
    resolved_model_path = _resolve_model_path(model_path)
    model = _load_model(resolved_model_path)

    try:
        predictions = model.predict(
            source=image_path,
            conf=YOLO_CONF_THRESHOLD,
            iou=YOLO_IOU_THRESHOLD,
            verbose=False,
        )
    except Exception as err:
        logger.exception("YOLO inference failed for naming analysis")
        raise VisionEngineError(f"YOLO naming analysis failed: {err}") from err

    if not predictions:
        raise VisionEngineError("YOLO model did not return predictions.")

    first_result = predictions[0]
    orig_shape = getattr(first_result, "orig_shape", None)
    if not orig_shape or len(orig_shape) < 2:
        raise VisionEngineError("Unable to resolve image dimensions from YOLO output.")

    image_height = int(orig_shape[0])
    image_width = int(orig_shape[1])
    if image_width <= 0 or image_height <= 0:
        raise VisionEngineError("YOLO returned invalid image dimensions.")

    names = getattr(first_result, "names", None) or getattr(model, "names", {}) or {}
    boxes = getattr(first_result, "boxes", None)

    assets: List[Dict[str, Any]] = []
    if boxes is not None:
        for idx, box in enumerate(boxes, start=1):
            xyxy_data = getattr(box, "xyxy", None)
            cls_data = getattr(box, "cls", None)
            conf_data = getattr(box, "conf", None)
            if xyxy_data is None or cls_data is None or conf_data is None:
                continue

            try:
                xyxy = xyxy_data[0].tolist()
                cls_id = int(float(cls_data[0].item()))
                confidence = float(conf_data[0].item())
            except Exception:
                continue

            if isinstance(names, dict):
                class_name = str(names.get(cls_id, f"class_{cls_id}"))
            elif isinstance(names, list) and 0 <= cls_id < len(names):
                class_name = str(names[cls_id])
            else:
                class_name = f"class_{cls_id}"
            assets.append(_build_asset(class_name, confidence, xyxy, image_width, image_height, idx))

    parsed_payload = _build_schema_payload(assets, resolved_model_path.name, image_width, image_height)

    warnings: List[str] = []
    if not assets:
        warnings.append("YOLO returned no detections above threshold for this image.")

    if assets:
        validated, validation_warnings = validate_response_schema(parsed_payload)
        warnings.extend(validation_warnings)
    else:
        # Keep true YOLO behavior: no detections means no boxes in the response.
        validated = parsed_payload

    transformed = _build_transformed_payload(validated)
    visualization_data_url = _build_visualization_data_url(first_result)
    response_extras: Dict[str, Any] = {}
    response_extras["naming_visualization_data_url"] = visualization_data_url

    raw_text = json.dumps(
        {
            "analysis_mode": "naming_analysis",
            "model_path": str(resolved_model_path),
            "detections": len(assets),
        }
    )

    return AnalysisResult(
        validated_response=validated,
        transformed=transformed,
        raw_text=raw_text,
        warnings=warnings,
        response_extras=response_extras,
    )
