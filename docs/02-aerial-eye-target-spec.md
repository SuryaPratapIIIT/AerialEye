# 02 - AerialEye Target Spec

## Product Core
**Discover → Analyze → Verify**
Search satellite imagery by meaning, discover relevant locations, understand what changed over time, and verify the evidence.

## Required Capabilities
1. **Semantic retrieval**: Natural language → ranked satellite imagery.
2. **Image-to-image retrieval**: Nearest neighbor similarity search.
3. **Multi-temporal analysis**: Before/after timeline, change map overlay, confidence score.
4. **False-alarm suppression**: OpenCV alignment and histogram normalization. Quality flags (cloud cover).
5. **Similar-site discovery**: Navigate to similar scenes from any asset.
6. **Analyst review**: Human-in-the-loop confirm/reject decision queue.
7. **Incremental ingestion**: Idempotent file ingest with metadata extraction.
8. **Offline operation**: Core features (CLIP, FAISS, SQLite, OpenCV) must run locally without cloud API requirements. (Groq API remains optional for legacy block analysis).
