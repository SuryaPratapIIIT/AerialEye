# AerialEye Core Engineering Rules

## Identity
Product: AerialEye
Core workflow: Discover → Analyze → Verify
Problem: SIH 26227 — Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery

## Data Honesty (MANDATORY)
- NEVER fabricate model outputs, detections, change scores, or confidence values
- NEVER claim offline when a cloud API is required
- Label every result with one of: REAL | HEURISTIC | DEMO | UNAVAILABLE
- When a capability is unavailable, show a clear labeled fallback — never silently mock

## Architecture Rules
- Preserve working code; only replace when justified
- SQLite for metadata (local, no server required)
- FAISS for vector index (local, offline-capable)
- CLIP ViT-B/32 for image embeddings; all-MiniLM-L6-v2 for text
- All indexes persist to disk (data/ directory)
- Groq VLM is labeled HEURISTIC in API responses and UI

## Frontend Rules
- Map-first workspace; analyst-oriented labels
- 5 primary nav tabs: Search | Analyze | Similar Sites | Review | Data
- Loading, empty, error, low-confidence states for every feature
- Existing pages (/, /detect, /gis) must remain working

## Backend Rules
- All new endpoints under /api/* with consistent error envelope
- SQLite DB at data/aerialeye.db (auto-created)
- FAISS index at data/faiss_index.bin (persisted after build)
- Ingestion is idempotent (SHA256 checksum dedup)
- Every result carries provenance: source, model_version, processing_ts
