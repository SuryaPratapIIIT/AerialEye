# AerialEye - Discover → Analyze → Verify

<img width="1536" height="864" alt="image" src="https://github.com/user-attachments/assets/e230d756-192d-4b4e-9cb3-3605b8da44ed" />

AerialEye is an end-to-end spatial analysis platform for satellite, aerial, and drone imagery.

It combines semantic retrieval, temporal change analysis, and human-in-the-loop analyst review into one unified local-first platform. It also preserves legacy block and naming analysis functionality.

## Core Capabilities

1. **Semantic Search**: Search for images using natural language (e.g., *"newly built structures near a river"*) powered by local CLIP embeddings and a FAISS vector index.
2. **Temporal Change Detection**: Compare scenes over time. AerialEye aligns scenes using ORB keypoint matching, normalizes illumination with histogram matching, and computes a heuristic change overlay.
3. **Analyst Review Queue**: Change candidates are queued for human review. Analysts can mark them as `Confirm`, `Reject`, or `Needs Review`.
4. **Similar Site Discovery**: Select any asset to instantly find similar locations via nearest-neighbor vector search.
5. **Local-First & Offline**: Built on SQLite, FAISS, OpenCV, and SentenceTransformers. Once models are cached locally on first run, all core discovery and analysis features operate entirely offline.
6. **Data Honesty**: All data, detections, and change scores are labeled with provenance (e.g., `REAL`, `HEURISTIC`, `DEMO`) ensuring analysts know the origin of the intelligence.

---

## The Workflow

### 1. Discover (`/search`)
Ingest imagery (TIFF, JPG, PNG) on the **Data** page. Then, navigate to **Search** to find relevant scenes using natural language or image similarity. Filter by date, source, and quality.

### 2. Analyze (`/analyze`)
Select a scene and view its temporal observations. Pick a "Before" and "After" scene. Click **Run Change Analysis** to perform image alignment and generate a change layer with a confidence score.

### 3. Verify (`/review`)
Generated candidates go to the **Review** queue. Analysts view the before/after/overlay evidence alongside provenance data to make a final verified decision.

---

## Technical Architecture

- **Frontend**: React 18, Vite, TailwindCSS, Framer Motion, Leaflet.
- **Backend**: FastAPI (Python 3).
- **Database**: SQLite (via `sqlite-utils`) for zero-config relational metadata.
- **Vector Search**: FAISS (Facebook AI Similarity Search) CPU-based indexing.
- **AI Models**: `openai/clip-vit-base-patch32` and `all-MiniLM-L6-v2` loaded locally via `sentence-transformers`.

---

## Setup & Running

### Prerequisites
- Node.js
- Python 3.9+
- Local python environment

### 1. Install Dependencies
```bash
# Frontend
npm install

# Backend
pip install -r requirements.txt
```

### 2. Configure Environment
Create/update a `.env` file at the project root:
```bash
# Required for frontend to reach backend
VITE_ANALYSIS_API_BASE=http://localhost:8000

# Optional: Vision API for legacy block analysis text reasoning
VISION_API_KEY=your_key_here
VISION_API_URL=https://api.groq.com/openai/v1/chat/completions
VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

# Legacy Naming analysis (YOLO)
YOLO_MODEL_PATH=./spatial_asset_yolo11n_best.pt
```

### 3. Start the Servers
Start both development servers in separate terminals (or concurrently):
```bash
# Starts FastAPI at http://localhost:8000
npm run dev:backend

# Starts Vite at http://localhost:5173
npm run dev:frontend
```

### 4. Seed Demo Data (First Run Only)
Run the demo seeder to generate synthetic satellite tiles, compute their embeddings, and index them. This enables you to immediately test search and change detection.
```bash
python scripts/seed_demo_data.py
```
> Note: First run will download the CLIP model weights (~350MB).

---

## Semantic retrieval (tiles, offline)

### Pre-download model weights (once, while online)

```bash
# CLIP ViT-B/32 (default)
huggingface-cli download openai/clip-vit-base-patch32 --local-dir models/clip-vit-base-patch32

# Optional: RemoteCLIP (place open_clip checkpoint)
# models/remoteclip/open_clip_pytorch_model.bin
```

Licence / origin are declared in `models/MODEL_CARD.json`. Runtime sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` and **will not download** if weights are missing.

### Ingest scenes then embed tiles

```bash
python ingest.py ./data/raw
python embed.py                          # uses embedding.model from config.yaml
python embed.py --model remoteclip --batch-size 64 --device cpu
python embed.py --watch                  # embed as Prompt 1 produces new tiles
```

Indexes are append-only FAISS `IndexIDMap2` files under `indexes/<model_name>.faiss` (IDs = `tiles.tile_id`). Raw vectors are also saved to `indexes/<model_name>_vectors.npy` for later clustering. New scenes only encode pending tiles — the index is never rebuilt during normal operation.

### Switch models

Edit `config.yaml`:

```yaml
embedding:
  model: "remoteclip"   # or "clip-vit-base-patch32"
```

Each model has its own index file; embedding spaces are not compatible. Re-run `embed.py` after switching so that model gets its own `tile_embeddings` rows.

### Search API

- `POST /api/search/text` — `{ "query", "k", "filters" }`
- `POST /api/search/image` — multipart file and/or `tile_id`
- `GET /api/tiles/{id}/similar`
- `POST /api/embed/run`
- `GET /api/index/status`
- `GET /api/models`

Default search returns **REAL** tiles only; set `include_legacy` / `include_demo` in filters to include others. Purge demo data with `python scripts/purge_demo.py --dry-run` (full purge rebuilds the index once — the only rebuild path).

### Benchmark / eval

```bash
python scripts/benchmark_search.py --queries scripts/queries.txt --k 10,20,50
python scripts/eval_search.py --csv scripts/eval_template.csv --k 5,10
```


## Project Documentation
Detailed implementation decisions, architecture overviews, and target specs can be found in the `/docs` directory.


## Change Detection Pipeline

### How the Pipeline Works
The new temporal change detection pipeline replaces the legacy ORB-based heuristic with a robust, staged, rule-based approach. It emphasizes precision over recall to suppress false alarms caused by clouds, shadows, seasonal changes, and misregistration.

### Stages and Their Purposes
1. **Common Grid**: Resamples and aligns before/after images to a shared CRS and resolution based on their overlapping footprints.
2. **Registration Refinement**: Estimates sub-pixel shifts using phase correlation on gradient-rich bands (like NIR) to correct minor alignment errors.
3. **Quality Masking**: Builds a joint invalid mask from Sentinel-2/Landsat product QA bands (clouds, shadows, snow) plus spectral haze safeguards and dilates them to catch edges.
4. **Radiometric Normalization**: Normalizes the 'after' image to the 'before' image using IR-MAD style iterative stable pixel selection and linear regression, or falls back to histogram matching.
5. **Indices and Differences**: Computes spectral indices (NDVI, NDBI, MNDWI, BSI) and calculates absolute differences and structural gradient differences, normalized by stable-pixel MAD sigma.
6. **Candidate Extraction**: Combines evidence into a weighted score, thresholds adaptively, extracts regions, and computes compactness and edge-alignment scores.
7. **Change Typing**: Applies explainable rules to assign a change type (e.g., construction, clearance, water extent variation, road development) and direction.
8. **False Alarm Suppression**: Suppresses candidates based on opposite seasons, phenology, single observations, cloud proximity, poor registration, and global illumination shifts.
9. **Confidence Scoring**: Assigns a confidence score (0-1) weighted by usable fraction, signal magnitude, persistence, registration quality, rule consistency, shape, and seasonal pairing.
10. **Earliest Supporting Observation**: For time-series, finds the earliest scene that supports the detected change using a step-fit changepoint algorithm on the target polygon.

### How to Tune It
All thresholds are located in config.yaml under the change: section. You can adjust:
- min_usable_fraction: To filter out heavily cloudy scenes early.
- score_weights: To prioritize certain indices (e.g., NDBI for urban).
- confidence_penalties: To strongly penalize candidates near clouds or with poor registration.
- bs_min_ndvi, bs_min_ndbi, etc.: To raise the floor for what constitutes a valid signal.

## Limitations
What this rule-based approach cannot do:
- **Semantic Nuance**: It cannot easily distinguish between functionally different but spectrally identical changes (e.g., a new warehouse roof vs. a large concrete parking lot).
- **Sub-pixel precision on complex shapes**: It relies on morphological operations and index thresholds, which may struggle with very thin features (e.g., footpaths) that don't trigger the minimum area or structural thresholds.
- **Severe Phenology without Baseline**: If the time series is sparse, distinguishing agricultural crop cycles from permanent clearance can still be difficult without a multi-year baseline.
- **Learning from Mistakes**: Being rule-based, it cannot automatically learn from analyst feedback without manual threshold adjustments in config.yaml.

## Assumptions
- The input imagery is generally georeferenced; the pipeline's registration stage is for *refinement* (sub-pixel or small pixel shifts), not large-scale matching.
- Masking products (like Sentinel-2 SCL or Landsat QA) are reasonably accurate but need dilation to be conservative.
- A 'stable' background exists in the pair for radiometric normalization (i.e., the entire AOI hasn't changed).
- Precision is strictly prioritized over recall.

