import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/webp",
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "video/mpeg",
}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".m4v"}
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
    version="1.0.0",
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
    logger.warning("CORS_ALLOW_CREDENTIALS=true is incompatible with wildcard origins. Forcing credentials off.")
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
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def _register_video_output(output_path: str) -> str:
    result_id = uuid.uuid4().hex
    VIDEO_RESULT_PATHS[result_id] = Path(output_path)
    return result_id


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "aerialeye-vision-analysis",
        "vision_api_key_loaded": bool(os.getenv("VISION_API_KEY")),
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
    logger.info(
        "Incoming analyze request id=%s mode=%s filename=%s content_type=%s",
        request_id,
        analysis_mode,
        image.filename,
        image.content_type,
    )

    if analysis_mode not in ANALYSIS_MODES:
        raise HTTPException(
            status_code=400,
            detail=_error_response(
                request_id,
                "invalid_analysis_mode",
                "Unsupported analysis mode.",
                f"Use one of: {', '.join(sorted(ANALYSIS_MODES))}. Received: {analysis_mode}",
            ),
        )

    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=_error_response(
                request_id,
                "invalid_image_type",
                "Unsupported image format. Use JPG, PNG, TIFF, or WEBP.",
                f"Received content type: {image.content_type}",
            ),
        )

    file_bytes = await image.read()
    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail=_error_response(
                request_id,
                "empty_file",
                "Uploaded image is empty.",
            ),
        )

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=_error_response(
                request_id,
                "file_too_large",
                "Uploaded file is too large.",
                f"Max allowed size: {MAX_UPLOAD_BYTES} bytes.",
            ),
        )

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

        # Apply single-image building height estimation from shadows using existing building detections.
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
            logger.warning("Height estimation step skipped for request id=%s: %s", request_id, height_err)
            result.warnings.append(f"Height estimation skipped: {height_err}")

        logger.info(
            "Analyze request complete id=%s mode=%s assets=%s warnings=%s",
            request_id,
            analysis_mode,
            len(result.validated_response.get("detected_assets", [])),
            len(result.warnings),
        )

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
        logger.exception("Vision analysis error id=%s", request_id)
        raise HTTPException(
            status_code=502,
            detail=_error_response(
                request_id,
                "vision_analysis_failed",
                "Vision AI analysis request failed.",
                str(err),
            ),
        ) from err
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Unexpected analysis failure id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail=_error_response(
                request_id,
                "internal_error",
                "Unexpected backend failure during analysis.",
                str(err),
            ),
        ) from err
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove temp file: %s", temp_path)


@app.post("/api/analyze-video")
async def analyze_video(
    request: Request,
    video: UploadFile = File(...),
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    logger.info(
        "Incoming video analyze request id=%s filename=%s content_type=%s",
        request_id,
        video.filename,
        video.content_type,
    )

    suffix = Path(video.filename or "uploaded_video.mp4").suffix.lower() or ".mp4"
    if video.content_type not in ALLOWED_VIDEO_TYPES and suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=_error_response(
                request_id,
                "invalid_video_type",
                "Unsupported video format. Use MP4, MOV, AVI, MKV, WEBM, MPEG, or M4V.",
                f"Received content type: {video.content_type}, extension: {suffix}",
            ),
        )

    file_bytes = await video.read()
    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail=_error_response(
                request_id,
                "empty_file",
                "Uploaded video is empty.",
            ),
        )

    if len(file_bytes) > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=_error_response(
                request_id,
                "file_too_large",
                "Uploaded video is too large.",
                f"Max allowed size: {MAX_VIDEO_UPLOAD_BYTES} bytes.",
            ),
        )

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
        if not output_file.exists() or not output_file.is_file():
            raise VisionEngineError("Processed video file is missing on disk.")

        result_id = _register_video_output(output_path)
        base = str(request.base_url).rstrip("/")
        video_result_url = f"{base}/api/video-results/{result_id}"

        logger.info(
            "Video analyze request complete id=%s frames_info=%s warnings=%s",
            request_id,
            result.response_extras.get("video_metadata", {}),
            len(result.warnings),
        )

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
        logger.exception("Video analysis error id=%s", request_id)
        raise HTTPException(
            status_code=502,
            detail=_error_response(
                request_id,
                "video_analysis_failed",
                "Video asset analysis request failed.",
                str(err),
            ),
        ) from err
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Unexpected video analysis failure id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail=_error_response(
                request_id,
                "internal_error",
                "Unexpected backend failure during video analysis.",
                str(err),
            ),
        ) from err
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove temp video file: %s", temp_path)
