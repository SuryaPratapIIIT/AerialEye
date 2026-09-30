---
name: AerialEye Core Rules
description: Engineering guidelines for AerialEye project development
---

# AerialEye - Engineering Guidelines

## Core Principles
1. **Local First**: AI inference, indexing, and data storage must happen on the local machine whenever possible to support offline operations. Relying on cloud APIs is permitted only as an optional fallback or for experimental capabilities (e.g., Groq VLM block analysis).
2. **Data Honesty**: Never fabricate metadata, detections, or confidence scores. All outputs must be traceable. Label fallbacks properly (e.g., `REAL`, `HEURISTIC`, `DEMO`).
3. **Idempotency**: Data ingestion, index updates, and migrations must be idempotent. Re-running the same job should not duplicate data.

## Technologies
- **Backend**: FastAPI (Python 3), Uvicorn, OpenCV (`cv2`), SQLite (`sqlite-utils`), FAISS (`faiss-cpu`), SentenceTransformers (`sentence-transformers`).
- **Frontend**: React 18, Vite, React Router, TailwindCSS, Framer Motion, Leaflet.

## File Organization
- `/backend/db.py`: Centralized SQLite database logic.
- `/backend/services/`: Service layer separating business logic (search, temporal, review) from API routes.
- `/src/pages/`: Main application views reflecting the Discover -> Analyze -> Verify workflow.
- `/data/`: Local storage for the `.db` file, `faiss_index.bin`, and ingested assets.

## Testing
Always maintain or extend the `backend/tests/` suite when adding API endpoints. Ensure tests run completely isolated from the production database by mocking `DB_PATH`.
