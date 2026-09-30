# Place model weights here for fully offline embedding.

## CLIP ViT-B/32
While online:
```bash
huggingface-cli download openai/clip-vit-base-patch32 --local-dir models/clip-vit-base-patch32
```
Or save an open_clip checkpoint as:
`models/clip-vit-base-patch32/open_clip_pytorch_model.bin`

## RemoteCLIP
Download the ViT-B-32 RemoteCLIP open_clip weights and place at:
`models/remoteclip/open_clip_pytorch_model.bin`

Then set `embedding.model: remoteclip` in config.yaml.

The runtime sets HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 and will raise
ModelWeightsMissingError if these folders are empty — it will never download.
