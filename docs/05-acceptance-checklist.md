# 05 - Acceptance Checklist

- [x] **Semantic Retrieval**: Natural language queries resolve via CLIP text-to-image embeddings.
- [x] **Image Retrieval**: Similar site identification uses FAISS vector search.
- [x] **Temporal Analysis**: Selected sites display observation timeline.
- [x] **Change Detection**: OpenCV aligns before/after images and highlights changed pixels.
- [x] **Analyst Review**: Candidates can be reviewed with a status of Confirm, Reject, or Needs Review.
- [x] **Data Honesty**: Seeded data is tagged with `DEMO`. Heuristic change maps tagged with `HEURISTIC`.
- [x] **Offline Operation**: Core ML models (CLIP, SentenceTransformers) and DB (SQLite, FAISS) run 100% locally.
- [x] **Test Coverage**: Pytest suite verifies DB deduplication, change map generation, and search queries.
- [x] **UI Completeness**: Dashboard has 5 core tabs reflecting the Discover -> Analyze -> Verify workflow.
