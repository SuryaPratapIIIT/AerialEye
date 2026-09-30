# 01 - Existing Project Audit

## Architecture Overview
The legacy repository was a detection and mapping platform for satellite imagery with:
- **Frontend**: React + Vite, TailwindCSS, Leaflet GIS map. Main routes were `/` (landing), `/detect`, and `/gis`.
- **Backend**: FastAPI (Python), handling block analysis (Groq VLM), naming analysis (YOLO), asset mapping (OpenCV contours), and video processing.
- **Storage**: No persistent database. State was mostly held in memory or local storage. Images saved directly to disk ad-hoc.

## Technical Debt & Gaps vs AerialEye
- **No Search**: No text-to-image semantic search. No vector index or embedding models.
- **No Persistence**: No SQLite or PostgreSQL registry for tracking scenes, analysis runs, or reviews.
- **No Temporal Workflow**: No way to compare scenes over time, register them, or run temporal change detection.
- **No Analyst Queue**: No human-in-the-loop review queue for candidate verification.

## Decisions
- **KEEP**: The FastAPI backend foundation, React frontend framework, Leaflet map components, OpenCV, and Ultralytics YOLO inference. The `/detect` and `/gis` pages will be preserved as legacy functionality.
- **EXTEND**: The FastAPI backend will be extended with 5 new core services (`db`, `embedding_service`, `ingestion_service`, `search_service`, `temporal_service`, `review_service`).
- **ADD**: SQLite database (`data/aerialeye.db`) for tracking metadata. FAISS CPU index for embedding search. CLIP ViT-B/32 for embeddings.
- **UI**: Add 5 new primary tabs: Search, Analyze, Similar Sites, Review, Data.
