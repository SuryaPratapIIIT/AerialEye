import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.services.vision_engine import VisionEngineError, _build_transformed_payload, analyze_spatial_image
from backend.services.naming_engine import analyze_naming_image
from backend.services.asset_map_engine import analyze_asset_map_image
from backend.services.video_asset_engine import analyze_asset_video
from height_estimation.utils import apply_height_estimation_to_analysis

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("aerialeye.backend")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/tiff", "image/webp",
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".m4v"}
ALLOWED_INGEST_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 500 * 1024 * 1024
ANALYSIS_MODES = {"block_analysis", "naming_analysis", "asset_map_analysis"}
VIDEO_OUTPUT_DIR = Path(tempfile.gettempdir()) / "aerialeye_video_outputs"
VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HEIGHT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "aerialeye_height_outputs"
HEIGHT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_RESULT_PATHS: Dict[str, Path] = {}

app = FastAPI(
    title="AerialEye Analysis API",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]
allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
if "*" in cors_origins and allow_credentials:
    logger.warning("CORS_ALLOW_CREDENTIALS=true incompatible with wildcard origins. Forcing off.")
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(request_id: str, code: str, message: str, details: str = "") -> Dict[str, Any]:
    return {
        "success": False,
        "request_id": request_id,
        "error": {"code": code, "message": message, "details": details},
    }


def _register_video_output(output_path: str) -> str:
    result_id = uuid.uuid4().hex
    VIDEO_RESULT_PATHS[result_id] = Path(output_path)
    return result_id


# =============================================================================
# LEGACY ENDPOINTS (preserved)
# =============================================================================

@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "message": "AerialEye Vision Analysis API v2.0 is running",
        "docs": "/api/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    try:
        from backend.db import get_db, get_index_stats
        db = get_db()
        stats = get_index_stats(db)
    except Exception:
        stats = {}
    return {
        "status": "ok",
        "service": "aerialeye-vision-analysis",
        "version": "2.0.0",
        "vision_api_key_loaded": bool(os.getenv("VISION_API_KEY")),
        "index_stats": stats,
    }


@app.get("/api/video-results/{result_id}")
def get_video_result(result_id: str) -> FileResponse:
    path = VIDEO_RESULT_PATHS.get(result_id)
    if path is None or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Video result not found or expired.")
    return FileResponse(path=path, media_type="video/mp4", filename=path.name)


@app.post("/api/analyze")
async def analyze_image(
    image: UploadFile = File(...),
    analysis_mode: str = Form("block_analysis"),
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    logger.info("Incoming analyze request id=%s mode=%s filename=%s", request_id, analysis_mode, image.filename)

    if analysis_mode not in ANALYSIS_MODES:
        raise HTTPException(
            status_code=400,
            detail=_error_response(request_id, "invalid_analysis_mode", "Unsupported analysis mode."),
        )
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=_error_response(request_id, "invalid_image_type", "Unsupported image format."),
        )

    file_bytes = await image.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail=_error_response(request_id, "empty_file", "Uploaded image is empty."))
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=_error_response(request_id, "file_too_large", "Uploaded file is too large."))

    suffix = Path(image.filename or "uploaded_image.jpg").suffix or ".jpg"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        if analysis_mode == "naming_analysis":
            result = analyze_naming_image(temp_path)
        elif analysis_mode == "asset_map_analysis":
            result = analyze_asset_map_image(temp_path)
        else:
            result = analyze_spatial_image(temp_path)

        try:
            height_update = apply_height_estimation_to_analysis(
                image_path=temp_path,
                validated_response=result.validated_response,
                response_extras=result.response_extras,
                request_id=request_id,
                output_root=str(HEIGHT_OUTPUT_DIR),
                meters_per_pixel=float(os.getenv("HEIGHT_METERS_PER_PIXEL", "0.2")),
                solar_elevation_angle=float(os.getenv("HEIGHT_SOLAR_ELEVATION_ANGLE", "45")),
            )
            result.validated_response = height_update["validated_response"]
            result.response_extras = height_update["response_extras"]
            result.warnings.extend(height_update["warnings"])
            result.transformed = _build_transformed_payload(result.validated_response)
        except Exception as height_err:
            logger.warning("Height estimation skipped for id=%s: %s", request_id, height_err)
            result.warnings.append(f"Height estimation skipped: {height_err}")

        response_payload = {
            "success": True,
            "request_id": request_id,
            "analysis_mode": analysis_mode,
            "data": result.validated_response,
            "transformed": result.transformed,
            "warnings": result.warnings,
        }
        if result.response_extras:
            response_payload.update(result.response_extras)
        return response_payload
    except VisionEngineError as err:
        raise HTTPException(status_code=502, detail=_error_response(request_id, "vision_analysis_failed", str(err))) from err
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=_error_response(request_id, "internal_error", str(err))) from err
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


@app.post("/api/analyze-video")
async def analyze_video(request: Request, video: UploadFile = File(...)) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    suffix = Path(video.filename or "uploaded_video.mp4").suffix.lower() or ".mp4"
    if video.content_type not in ALLOWED_VIDEO_TYPES and suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=_error_response(request_id, "invalid_video_type", "Unsupported video format."))

    file_bytes = await video.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail=_error_response(request_id, "empty_file", "Uploaded video is empty."))
    if len(file_bytes) > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=_error_response(request_id, "file_too_large", "Uploaded video is too large."))

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        result = analyze_asset_video(temp_path, str(VIDEO_OUTPUT_DIR))
        output_path = str(result.response_extras.get("video_output_path", "")).strip()
        if not output_path:
            raise VisionEngineError("Video processing completed without output path.")
        output_file = Path(output_path)
        if not output_file.exists():
            raise VisionEngineError("Processed video file is missing on disk.")

        result_id = _register_video_output(output_path)
        base = str(request.base_url).rstrip("/")
        video_result_url = f"{base}/api/video-results/{result_id}"

        response_payload = {
            "success": True,
            "request_id": request_id,
            "analysis_mode": "video_analysis",
            "data": result.validated_response,
            "transformed": result.transformed,
            "warnings": result.warnings,
            "video_result_url": video_result_url,
        }
        for key, value in result.response_extras.items():
            if key == "video_output_path":
                continue
            response_payload[key] = value
        return response_payload
    except VisionEngineError as err:
        raise HTTPException(status_code=502, detail=_error_response(request_id, "video_analysis_failed", str(err))) from err
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=_error_response(request_id, "internal_error", str(err))) from err
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


# =============================================================================
# NEW AERIALEYE ENDPOINTS
# =============================================================================

# --- Ingestion ---

@app.post("/api/ingest")
async def ingest_image(
    image: UploadFile = File(...),
    sensor: str = Form("unknown"),
    acquisition_time: Optional[str] = Form(None),
    label: str = Form("REAL"),
    tags: str = Form("[]"),
) -> Dict[str, Any]:
    """Ingest an image/GeoTIFF into the AerialEye search index."""
    suffix = Path(image.filename or "upload.jpg").suffix.lower()
    if suffix not in ALLOWED_INGEST_EXTENSIONS and suffix not in {".tif", ".tiff"}:
        raise HTTPException(status_code=400, detail={"error": "Unsupported file type for ingestion."})

    file_bytes = await image.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail={"error": "Empty file."})
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"error": "File too large (max 50MB)."})

    try:
        import json as _json
        tag_list = _json.loads(tags) if tags else []
    except Exception:
        tag_list = []

    from backend.services.ingestion_service import ingest_file
    result = ingest_file(
        file_bytes=file_bytes,
        filename=image.filename or "upload.jpg",
        sensor=sensor,
        acquisition_time=acquisition_time,
        label=label,
        tags=tag_list,
    )
    return {"success": True, **result}


# --- Search ---

@app.get("/api/search")
def semantic_search(
    q: str = Query(..., description="Natural language search query"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sensor: Optional[str] = Query(None),
    min_quality: float = Query(0.0, ge=0.0, le=1.0),
    top_k: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Semantic natural-language search over indexed imagery."""
    from backend.services.search_service import text_search
    return text_search(
        query=q,
        date_from=date_from,
        date_to=date_to,
        sensor=sensor,
        min_quality=min_quality,
        top_k=top_k,
    )


@app.post("/api/search/image")
async def image_similarity_search(
    image: Optional[UploadFile] = File(None),
    tile_id: Optional[int] = Form(None),
    date_from: Optional[str] = Form(None),
    date_to: Optional[str] = Form(None),
    sensor: Optional[str] = Form(None),
    min_quality: float = Form(0.0),
    top_k: int = Form(20),
    k: Optional[int] = Form(None),
    filters_json: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """Image-to-image similarity search (multipart file and/or tile_id)."""
    import json as _json
    from backend.services.search_service import search_image

    filters: Dict[str, Any] = {}
    if filters_json:
        try:
            filters = _json.loads(filters_json)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid filters_json: {exc}") from exc
    if date_from:
        filters.setdefault("date_from", date_from)
    if date_to:
        filters.setdefault("date_to", date_to)
    if sensor:
        filters.setdefault("sensors", [sensor])
    if min_quality and min_quality > 0:
        filters.setdefault("min_valid_fraction", min_quality)

    kk = k or top_k or 20
    if tile_id is not None and image is None:
        return search_image(tile_id=int(tile_id), k=kk, filters=filters)
    if image is None:
        raise HTTPException(status_code=422, detail="Provide multipart file and/or tile_id.")

    file_bytes = await image.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Empty file.")

    suffix = Path(image.filename or "query.jpg").suffix or ".jpg"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(file_bytes)
            temp_path = f.name
        return search_image(image_path=temp_path, k=kk, filters=filters, tile_id=tile_id)
    finally:
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink(missing_ok=True)


# --- Temporal / Change ---

@app.get("/api/scenes/{asset_id}/observations")
def get_observations(asset_id: str) -> Dict[str, Any]:
    """Get temporal observations for a scene location."""
    from backend.services.temporal_service import get_temporal_observations
    return get_temporal_observations(asset_id)


@app.post("/api/change-analysis")
def run_change_analysis(
    asset_id_before: str = Form(...),
    asset_id_after: str = Form(...),
) -> Dict[str, Any]:
    """Run temporal change detection between two scenes."""
    from backend.services.temporal_service import run_change_analysis
    return run_change_analysis(asset_id_before, asset_id_after)


# --- Similar Sites ---

@app.get("/api/similar-sites/{asset_id}")
def get_similar_sites(
    asset_id: str,
    top_k: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Find visually/semantically similar scenes to a given asset."""
    from backend.services.search_service import similar_sites
    return similar_sites(asset_id, top_k=top_k)


# --- Review ---

@app.get("/api/review/queue")
def get_review_queue(
    status: Optional[str] = Query(None, description="Filter by status: NEW, CONFIRMED, REJECTED, NEEDS_REVIEW"),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Get the analyst review queue."""
    from backend.services.review_service import get_review_queue
    return get_review_queue(status_filter=status, limit=limit)


@app.get("/api/review/candidates/{candidate_id}")
def get_candidate_detail(candidate_id: str) -> Dict[str, Any]:
    """Get full detail and provenance for a change candidate."""
    from backend.services.review_service import get_candidate_detail
    return get_candidate_detail(candidate_id)


@app.post("/api/review/{candidate_id}/decision")
def submit_decision(
    candidate_id: str,
    status: str = Form(...),
    notes: str = Form(""),
    analyst_id: str = Form("anonymous"),
) -> Dict[str, Any]:
    """Submit an analyst decision for a change candidate."""
    from backend.services.review_service import submit_decision
    return submit_decision(candidate_id=candidate_id, status=status, notes=notes, analyst_id=analyst_id)


# --- Data / Status ---

@app.get("/api/data/status")
def get_data_status() -> Dict[str, Any]:
    """Return index statistics, model health, and ingestion history."""
    try:
        from backend.db import get_db, get_index_stats
        from backend.services.embedding_service import get_models_status
        db = get_db()
        stats = get_index_stats(db)
        model_status = get_models_status()
    except Exception as exc:
        stats = {}
        model_status = {"error": str(exc)}

    yolo_path = os.getenv("YOLO_MODEL_PATH", "./spatial_asset_yolo11n_best.pt")
    yolo_available = Path(yolo_path).exists()

    return {
        "index_stats": stats,
        "model_status": model_status,
        "yolo_available": yolo_available,
        "yolo_model_path": yolo_path,
        "vision_api_key_loaded": bool(os.getenv("VISION_API_KEY")),
        "data_dir": str(Path("data").resolve()),
    }


from pydantic import BaseModel
from backend.schemas import (
    TextSearchRequest,
    ImageSearchJsonRequest,
    EmbedRunRequest,
    SearchFilters,
    ChangeRunRequest,
)


class IngestRequest(BaseModel):
    folder: str


@app.post("/api/ingest/folder")
def trigger_ingest(req: IngestRequest) -> Dict[str, Any]:
    from backend.services.geospatial_ingestion import process_folder
    import os
    if not os.path.exists(req.folder):
        raise HTTPException(status_code=400, detail="Folder does not exist")
    res = process_folder(req.folder)
    return {"success": True, "results": res}


@app.get("/api/scenes")
def get_all_geo_scenes() -> Dict[str, Any]:
    from backend.repository import GeoRepository
    repo = GeoRepository()
    rows = list(repo.db["geo_scenes"].rows_where(order_by="acquisition_datetime DESC"))
    return {"scenes": rows, "total": len(rows)}


@app.get("/api/scenes/{scene_id}/tiles")
def get_scene_tiles(scene_id: str) -> Dict[str, Any]:
    from backend.repository import GeoRepository
    repo = GeoRepository()
    tiles = repo.get_tiles_for_scene(scene_id)
    return {"tiles": tiles, "total": len(tiles)}


# --- Prompt 2: tile semantic search / embed / index ---

@app.post("/api/search/text")
def api_search_text(req: TextSearchRequest) -> Dict[str, Any]:
    """Free-text semantic search over embedded tiles."""
    from backend.services.search_service import search_text

    filters = req.filters.model_dump(exclude_none=True) if req.filters else {}
    return search_text(query=req.query, k=req.k, filters=filters)


@app.post("/api/search/image/json")
def api_search_image_json(req: ImageSearchJsonRequest) -> Dict[str, Any]:
    from backend.services.search_service import search_image

    filters = req.filters.model_dump(exclude_none=True) if req.filters else {}
    return search_image(tile_id=req.tile_id, k=req.k, filters=filters)


@app.get("/api/tiles/{tile_id}/similar")
def api_tile_similar(
    tile_id: int,
    k: int = Query(10, ge=1, le=200),
    include_legacy: bool = Query(False),
    include_demo: bool = Query(False),
    max_cloud_fraction: Optional[float] = Query(None),
    min_valid_fraction: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
) -> Dict[str, Any]:
    from backend.services.search_service import similar_tiles

    filters = {
        "include_legacy": include_legacy,
        "include_demo": include_demo,
        "max_cloud_fraction": max_cloud_fraction,
        "min_valid_fraction": min_valid_fraction,
        "date_from": date_from,
        "date_to": date_to,
    }
    filters = {kk: vv for kk, vv in filters.items() if vv is not None}
    return similar_tiles(tile_id, k=k, filters=filters)


@app.get("/api/tiles/{tile_id}/preview")
def api_tile_preview(tile_id: int) -> FileResponse:
    from backend.repository import GeoRepository

    repo = GeoRepository()
    tile = repo.get_tile(tile_id)
    if not tile or not tile.get("preview_path"):
        raise HTTPException(status_code=404, detail="Tile preview not found")
    path = Path(tile["preview_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview file missing on disk")
    return FileResponse(path=path, media_type="image/png")


@app.post("/api/embed/run")
def api_embed_run(req: EmbedRunRequest) -> Dict[str, Any]:
    from backend.services.embedding_service import run_incremental_embed

    stats = run_incremental_embed(
        model_name=req.model,
        batch_size=req.batch_size,
        device=req.device,
        limit=req.limit,
    )
    return {"success": True, **stats}


@app.get("/api/index/status")
def api_index_status(model: Optional[str] = Query(None)) -> Dict[str, Any]:
    from backend.services.embedding_service import get_index_status

    return get_index_status(model)


@app.get("/api/models")
def api_models() -> Dict[str, Any]:
    from backend.services.embedding_models import load_model_cards
    from backend.services.embedding_service import get_embedding_config

    cards = load_model_cards()
    return {
        "active_model": get_embedding_config().get("model"),
        "models": cards,
    }


# --- Prompt 3: change detection ---

@app.post("/api/change/run")
def api_change_run(req: ChangeRunRequest, background_tasks: Any = None) -> Dict[str, Any]:
    """Start a change-detection run (background by default)."""
    from fastapi import BackgroundTasks
    from backend.services.change.repository import ChangeRepository
    from backend.services.change.pipeline import execute_change_run, PROGRESS
    from backend.services.change.config import load_change_config
    import numpy as np

    cfg = load_change_config()
    repo = ChangeRepository()
    run_id = repo.create_run({
        "aoi": req.aoi,
        "date_from": req.date_from,
        "date_to": req.date_to,
        "mode": req.mode,
        "params": req.model_dump(),
        "pipeline_version": cfg.get("pipeline_version"),
    })

    def band_loader(scene_id: str):
        from backend.repository import GeoRepository
        geo = GeoRepository()
        tiles = geo.get_tiles_for_scene(scene_id)
        if not tiles:
            raise FileNotFoundError(f"No tiles for {scene_id}")
        t = tiles[0]
        chip = np.load(t["chip_path"])
        if chip.ndim == 3 and chip.shape[0] <= 12:
            bands = {}
            names = ["B02", "B03", "B04", "B08", "B11"]
            for i, n in enumerate(names):
                if i < chip.shape[0]:
                    bands[n] = chip[i].astype(np.float32)
                    if float(np.nanmax(bands[n])) > 1.5:
                        bands[n] = bands[n] / 10000.0
            if "B08" not in bands and "B03" in bands:
                bands["B08"] = bands["B03"]
            if "B11" not in bands and "B04" in bands:
                bands["B11"] = bands["B04"] * 0.9
            return bands
        arr = chip
        if arr.ndim == 3 and arr.shape[-1] >= 3:
            r, g, b = arr[..., 0].astype(np.float32), arr[..., 1].astype(np.float32), arr[..., 2].astype(np.float32)
            if r.max() > 1.5:
                r, g, b = r / 255.0, g / 255.0, b / 255.0
            return {"B04": r, "B03": g, "B02": b, "B08": g, "B11": r * 0.8}
        raise ValueError("Unsupported chip")

    def _job():
        execute_change_run(
            run_id,
            aoi=req.aoi,
            date_from=req.date_from,
            date_to=req.date_to,
            mode=req.mode,
            before_scene_id=req.before_scene_id,
            after_scene_id=req.after_scene_id,
            sensor=req.sensor,
            include_low_confidence=req.include_low_confidence,
            band_loader=band_loader,
            cfg=cfg,
        )

    if req.background:
        # Use FastAPI BackgroundTasks via request injection workaround
        from starlette.background import BackgroundTasks as BT
        # Schedule via threading to avoid signature issues
        import threading
        threading.Thread(target=_job, daemon=True).start()
        return {"success": True, "run_id": run_id, "status": "pending", "progress_url": f"/api/change/runs/{run_id}/progress"}

    result = _job() or {}
    return {"success": True, "run_id": run_id, **(result if isinstance(result, dict) else {})}


@app.get("/api/change/runs/{run_id}")
def api_change_run_status(run_id: str) -> Dict[str, Any]:
    from backend.services.change.repository import ChangeRepository
    import json as _json

    repo = ChangeRepository()
    row = repo.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    summary = {}
    try:
        summary = _json.loads(row.get("summary_json") or "{}")
    except Exception:
        pass
    return {
        "run_id": run_id,
        "status": row.get("status"),
        "progress": row.get("progress"),
        "message": row.get("message"),
        "params": _json.loads(row.get("params_json") or "{}"),
        "summary": summary,
        "pipeline_version": row.get("pipeline_version"),
        "error": row.get("error"),
    }


@app.get("/api/change/runs/{run_id}/progress")
def api_change_progress(run_id: str) -> Dict[str, Any]:
    from backend.services.change.pipeline import PROGRESS
    from backend.services.change.repository import ChangeRepository

    if run_id in PROGRESS:
        return {"run_id": run_id, **PROGRESS[run_id]}
    repo = ChangeRepository()
    row = repo.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": run_id,
        "progress": row.get("progress"),
        "message": row.get("message"),
        "status": row.get("status"),
    }


@app.get("/api/change/runs/{run_id}/candidates")
def api_change_candidates(
    run_id: str,
    change_type: Optional[str] = Query(None),
    confidence_label: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
) -> Dict[str, Any]:
    from backend.services.change.repository import ChangeRepository

    repo = ChangeRepository()
    rows = repo.list_candidates(
        run_id,
        change_type=change_type,
        confidence_label=confidence_label,
        review_status=review_status,
    )
    return {"run_id": run_id, "candidates": rows, "total": len(rows)}


@app.get("/api/change/runs/{run_id}/suppressed")
def api_change_suppressed(run_id: str) -> Dict[str, Any]:
    from backend.services.change.repository import ChangeRepository

    repo = ChangeRepository()
    rows = repo.list_candidates(run_id, suppressed=True)
    return {"run_id": run_id, "suppressed": rows, "total": len(rows)}


@app.get("/api/change/candidates/{candidate_id}")
def api_change_candidate_detail(candidate_id: str) -> Dict[str, Any]:
    from backend.services.change.repository import ChangeRepository
    import json as _json

    repo = ChangeRepository()
    row = repo.get_candidate(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="candidate not found")
    # Expand JSON fields
    for key in ("geometry_geojson", "confidence_breakdown_json", "evidence_json",
                "suppression_reasons_json", "skipped_scenes_json"):
        if key in row and isinstance(row[key], str):
            try:
                row[key.replace("_json", "") if key.endswith("_json") else key] = _json.loads(row[key])
            except Exception:
                pass
    run = repo.get_run(row["run_id"])
    return {
        "candidate": row,
        "run_provenance": _json.loads(run["provenance_json"]) if run and run.get("provenance_json") else {},
    }
