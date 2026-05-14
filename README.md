# AerialEye - AI-Powered Spatial Asset Management System

AerialEye is an end-to-end spatial analysis platform for satellite, aerial, and drone imagery/video.
It combines frontend visualization, backend AI/CV processing, GIS-ready outputs, and building-height estimation from shadows.

The project currently supports:
- Image upload + analysis
- Video upload + analysis
- Multi-mode detection workflows
- Overlay rendering and interactive frontend visualization
- Area/count summaries and building-height metrics
- GIS export (GeoJSON + CSV)
- Processed video export + metadata JSON-style payloads

## Implemented Analysis Modes

### 1) Block Analysis (`block_analysis`)
- Endpoint: `POST /api/analyze` with `analysis_mode=block_analysis`
- Pipeline:
  - Tries VLM-based analysis (Groq/OpenAI-compatible chat completion endpoint)
  - Normalizes and validates schema
  - Recomputes category stats and transformed frontend payload
  - Uses local heuristic pixel-block generation for robust, synchronized mapped assets
- Output:
  - Structured JSON (`data`, `transformed`)
  - Frontend-renderable normalized geometry (0..100 coordinate system)

### 2) Naming Analysis (`naming_analysis`)
- Endpoint: `POST /api/analyze` with `analysis_mode=naming_analysis`
- Model: `spatial_asset_yolo11n_best.pt` (Ultralytics YOLO)
- Pipeline:
  - Loads YOLO model (cached)
  - Runs inference with configurable confidence/IoU thresholds
  - Maps YOLO classes to project categories
  - Builds normalized assets + statistics
  - Returns YOLO-rendered frame as visualization data URL
- Output extras:
  - `naming_visualization_data_url`

### 3) Asset Map (`asset_map_analysis`)
- Endpoint: `POST /api/analyze` with `analysis_mode=asset_map_analysis`
- Pipeline:
  - OpenCV/Numpy based semantic mask extraction
  - Morphological cleanup + contour extraction
  - Category-wise object generation and area/coverage computation
  - Blended asset map overlay generation
- Output extras:
  - `asset_map_visualization_data_url`

### 4) Video Analysis (`video_analysis`)
- Endpoint: `POST /api/analyze-video`
- Pipeline:
  - Frame-by-frame OpenCV-based asset detection
  - Frame stride + resize knobs for performance tuning
  - Overlay drawing + info panel in output video
  - Aggregated counts/coverage metadata in response
- Output extras:
  - `video_result_url` (download/stream via backend)
  - `video_metadata` (`processed_frames`, `detected_frames`, `fps`, `frame_stride`, etc.)

## New Feature: Building Height Estimation (Shadow-Based 3D Approximation)

Height estimation is integrated automatically in the image analysis pipeline and runs after each image mode.

### Where it runs
- Integrated in `backend/main.py` inside `POST /api/analyze` after base analysis output is prepared.
- Reuses already detected building assets (does not launch a separate building detector when building boxes already exist).

### Core formula
- `H = S * tan(theta)`
- `S`: shadow length in meters
- `theta`: solar elevation angle

### Implemented module
```text
height_estimation/
  detector.py
  shadow_analysis.py
  geometry.py
  visualization.py
  utils.py
```

### What gets added per building
- `shadow_length_pixels`
- `shadow_length_meters`
- `estimated_height_meters`

### Additional output artifacts
- `analyzed_output.jpg` (height overlay image)
- `results.json` (building-level height records)
- API extras:
  - `height_visualization_data_url`
  - `height_estimation_output_path`
  - `height_estimation_json_path`
  - `height_estimation_config`

## Frontend Integration

Main detection UI: `src/pages/Detect.tsx`

Implemented behavior:
- Upload image/video
- Mode selection buttons:
  - `Block Analysis`
  - `Naming Analysis`
  - `Asset Map`
  - `Video Analysis`
- Result rendering:
  - Image overlay (for image modes)
  - Processed video playback (for video mode)
- Right-side summary card:
  - Area/count by category
  - Total objects
  - Total area (`m2`)
  - Building-height summary (`count`, `avg|min|max`)
- Bottom-left strip:
  - Coordinates
  - Mapped count
  - Average building height
- Tooltip/hover card:
  - Per-asset details including `estimated_height_meters` when available

GIS page (`/gis`):
- Reads latest analysis from local storage
- Layer toggles, markers, polygons
- GeoJSON export

## Backend API

### Health
- `GET /api/health`

### Image analysis
- `POST /api/analyze`
- Form fields:
  - `image` (JPG/PNG/TIFF/WEBP)
  - `analysis_mode` in:
    - `block_analysis`
    - `naming_analysis`
    - `asset_map_analysis`

### Video analysis
- `POST /api/analyze-video`
- Form field:
  - `video` (MP4/MOV/AVI/MKV/WEBM/MPEG/M4V)

### Video result fetch
- `GET /api/video-results/{result_id}`

## Data Contracts

Core response:
- `success`
- `request_id`
- `data` (structured analysis)
- `transformed` (frontend/GIS payload)
- `warnings`

Height-enhanced asset item (building entries):
```json
{
  "class": "building",
  "bbox": [x1, y1, x2, y2],
  "shadow_length_pixels": 120,
  "shadow_length_meters": 24,
  "estimated_height_meters": 18.5
}
```

Video response also includes:
- `video_result_url`
- `video_metadata`

## Project Structure

```text
backend/
  main.py
  services/
    vision_engine.py
    naming_engine.py
    asset_map_engine.py
    video_asset_engine.py
    area_utils.py

height_estimation/
  detector.py
  shadow_analysis.py
  geometry.py
  visualization.py
  utils.py

src/
  pages/
    Detect.tsx
    GIS.tsx
    Landing.tsx
  utils/api.ts
  types/analysis.ts
```

## Setup

## 1) Install frontend dependencies
```bash
npm install
```

## 2) Install backend dependencies
```bash
pip install -r requirements.txt
```

## 3) Configure environment variables

Create/update `.env` (example values):
```bash
# External vision API for block analysis text reasoning
VISION_API_KEY=your_key_here
VISION_API_URL=https://api.groq.com/openai/v1/chat/completions
VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

# Frontend -> backend base URL
VITE_ANALYSIS_API_BASE=http://localhost:8000

# Area calibration
METERS_PER_PIXEL=1.0

# Naming analysis (YOLO)
YOLO_MODEL_PATH=./spatial_asset_yolo11n_best.pt
YOLO_CONF_THRESHOLD=0.25
YOLO_IOU_THRESHOLD=0.45

# Height estimation
HEIGHT_METERS_PER_PIXEL=0.2
HEIGHT_SOLAR_ELEVATION_ANGLE=45

# Video performance tuning
VIDEO_ANALYSIS_FRAME_STRIDE=2
VIDEO_ANALYSIS_TARGET_DETECTION_FRAMES=300
VIDEO_ANALYSIS_MAX_DETECTION_DIM=960

# CORS
CORS_ALLOW_ORIGINS=*
CORS_ALLOW_CREDENTIALS=false
```

## 4) Run backend
```bash
npm run dev:backend
```

## 5) Run frontend
```bash
npm run dev:frontend
```

Default ports:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

## Exported Outputs

- GeoJSON export from frontend result/GIS view
- CSV export from frontend result view
- Processed output video from video analysis endpoint
- Height-estimation artifacts:
  - `analyzed_output.jpg`
  - `results.json`

## Performance Notes

For faster video completion:
- Increase `VIDEO_ANALYSIS_FRAME_STRIDE`
- Lower `VIDEO_ANALYSIS_MAX_DETECTION_DIM`
- Keep `VIDEO_ANALYSIS_TARGET_DETECTION_FRAMES` moderate

Trade-off:
- Higher speed can reduce temporal/spatial detail.

## Assumptions and Limitations

### Spatial area metrics
- Area in `m2` depends on `METERS_PER_PIXEL`.
- Different modes may produce different area totals because they use different detection strategies:
  - heuristic blocks vs YOLO boxes vs CV masks vs frame-level aggregates.

### Height estimation constraints
- Single-image shadow analysis is an approximation.
- Sensitive to:
  - sun angle assumptions
  - shadow visibility/occlusion
  - low contrast
  - top-down scenes with weak cast shadows
- Current visualization is 2D overlay with geometric cues (bbox, contour, direction line, label), not full mesh-based 3D reconstruction.

### Video counting semantics
- Current video counts represent detection events over analyzed frames (not persistent multi-object identity tracking IDs).

## Troubleshooting

### `HTTP 502` / `Unable to reach analysis service`
1. Ensure backend is running:
   - `npm run dev:backend`
2. Verify frontend base URL:
   - `VITE_ANALYSIS_API_BASE=http://localhost:8000`
3. Check model/dependency availability:
   - `pip install -r requirements.txt`
   - YOLO `.pt` file exists at configured path.
4. Check upload size/type limits:
   - image max `50 MB`
   - video max `500 MB`

### Build checks
```bash
npm run build
npx tsc --noEmit
```

## Roadmap / Future Upgrades

- Visual doodle-driven analysis interaction
- Real-time video segmentation pipeline (streaming)
- Stronger multi-frame temporal smoothing for height estimates
- Persistent tracked IDs in video analytics
- WebODM integration (orthophoto + DSM/DTM workflow)
- Stereo / depth-assisted height estimation for improved 3D reliability

## Security Note

Do not commit real API keys into source control. Use environment variables or secret management for production deployments.
