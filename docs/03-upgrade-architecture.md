# 03 - Upgrade Architecture

## Tech Stack
- **Database**: SQLite (managed via `sqlite-utils`) stored at `data/aerialeye.db`. Local, zero-config, single-file.
- **Search Index**: FAISS (Facebook AI Similarity Search) CPU index stored at `data/faiss_index.bin`. High performance local vector search.
- **Embeddings**: `sentence-transformers` running `openai/clip-vit-base-patch32` (images and semantic text) and `all-MiniLM-L6-v2` (text fallback).
- **Temporal/Change**: OpenCV (`cv2`) using ORB for feature matching/alignment, histogram matching for radiometric normalization, and absolute pixel differences for heuristic change detection.
- **Frontend**: React, Vite, TailwindCSS.

## Services Layer
- `db.py`: Database connection and initialization.
- `embedding_service.py`: Loads local AI models and manages the FAISS index.
- `ingestion_service.py`: Idempotent image processing, thumbnail generation, and metadata extraction.
- `search_service.py`: Vector cosine similarity search.
- `temporal_service.py`: Computes before/after alignment and outputs change confidence and change maps.
- `review_service.py`: Tracks analyst decisions on change candidates.

## Data Model
- `scenes`: Image metadata, timestamps, paths.
- `change_candidates`: Registered before/after pairs with change scores and base64 encoded change maps.
- `analyst_decisions`: Audit trail of human reviews on candidates.
