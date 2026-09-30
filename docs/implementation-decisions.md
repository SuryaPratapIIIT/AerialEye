# Implementation Decisions

1. **Storage Choice**: Kept it simple with SQLite (via `sqlite-utils`) for relational metadata and a local FAISS index (`faiss-cpu`) for embeddings. This avoids standing up a Postgres/pgvector server, ensuring the app runs locally easily.
2. **Models**: Selected `openai/clip-vit-base-patch32` as the image/text embedding model for semantic search. Selected `all-MiniLM-L6-v2` as a fast text-only fallback.
3. **Change Detection Heuristics**: Deep learning models for change detection are large and fragile without specialized training. Decided to build a robust heuristic baseline using OpenCV: ORB keypoint matching for image alignment, histogram matching to normalize lighting differences, and absolute pixel differences to flag changes. This runs entirely locally.
4. **Data Honesty**: Since the project lacked real temporal satellite imagery, a script (`scripts/seed_demo_data.py`) was written to procedurally generate synthetic satellite tiles to prove the pipelines work end-to-end. These are explicitly tagged as `DEMO` in the DB.
5. **Legacy Preservation**: The original `/detect` and `/gis` pages and their backend routes were completely preserved and isolated from the new AerialEye components so the user does not lose existing functionality.
