"""
Offline embedding model abstraction for AerialEye.

HARD RULE: Set HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 before importing
model libraries. Weights must exist under models/<name>/ — never download.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Sequence

# Offline before any HF / transformers import
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

import numpy as np

logger = logging.getLogger("aerialeye.models")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
MODEL_CARD_PATH = MODELS_DIR / "MODEL_CARD.json"


class ModelWeightsMissingError(RuntimeError):
    """Raised when local model weights are missing (no network fallback)."""


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (vectors / norms).astype(np.float32)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class EmbeddingModel(ABC):
    name: str
    version: str
    embedding_dim: int
    licence: str
    source_url: str

    @abstractmethod
    def encode_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        """Encode RGB uint8 HWC arrays -> float32 [N, D] L2-normalised."""

    @abstractmethod
    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        """Encode strings -> float32 [M, D] L2-normalised."""

    def model_card(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "embedding_dim": self.embedding_dim,
            "licence": self.licence,
            "source_url": self.source_url,
        }


class FakeEmbeddingModel(EmbeddingModel):
    """Deterministic colour-histogram embedding for offline unit tests."""

    name = "fake-hist"
    version = "1.0.0"
    embedding_dim = 64
    licence = "Apache-2.0"
    source_url = "local://tests/fake-hist"

    def __init__(self, dim: int = 64):
        self.embedding_dim = dim

    def encode_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        out = []
        for img in images:
            arr = np.asarray(img)
            if arr.ndim == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
            # Simple per-channel mean + std + coarse hist → fixed dim
            flat = arr.astype(np.float32).reshape(-1, arr.shape[-1])
            means = flat.mean(axis=0)
            stds = flat.std(axis=0) + 1e-6
            hist = []
            for c in range(min(3, flat.shape[1])):
                h, _ = np.histogram(flat[:, c], bins=16, range=(0, 255), density=True)
                hist.append(h)
            vec = np.concatenate([means, stds, *hist]).astype(np.float32)
            if vec.size < self.embedding_dim:
                vec = np.pad(vec, (0, self.embedding_dim - vec.size))
            else:
                vec = vec[: self.embedding_dim]
            # Mix in a content hash for uniqueness
            digest = hashlib.md5(arr.tobytes()[:4096]).digest()
            noise = np.frombuffer(digest * ((self.embedding_dim // 16) + 1), dtype=np.uint8)[
                : self.embedding_dim
            ].astype(np.float32) / 255.0
            vec = 0.7 * vec + 0.3 * noise
            out.append(vec)
        return _l2_normalize(np.stack(out, axis=0))

    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        out = []
        for t in texts:
            digest = hashlib.sha256(t.lower().encode("utf-8")).digest()
            # Expand digest to dim
            reps = (self.embedding_dim // len(digest)) + 1
            raw = (digest * reps)[: self.embedding_dim]
            vec = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 255.0
            # Boost tokens that match common landcover words for weak semantic signal
            for i, word in enumerate(["river", "farm", "village", "cloud", "forest", "urban"]):
                if word in t.lower():
                    vec[i % self.embedding_dim] += 0.5
            out.append(vec)
        return _l2_normalize(np.stack(out, axis=0))


class CLIPViTB32Model(EmbeddingModel):
    """
    OpenAI CLIP ViT-B/32 loaded exclusively from models/clip-vit-base-patch32/.
    Uses open_clip if available, else sentence-transformers / transformers offline.
    """

    name = "clip-vit-base-patch32"
    version = "openai-vit-b-32-1.0"
    embedding_dim = 512
    licence = "MIT"
    source_url = "https://huggingface.co/openai/clip-vit-base-patch32"

    def __init__(self, device: str = "cpu", models_dir: Optional[Path] = None):
        self.device = device
        self.root = Path(models_dir or MODELS_DIR) / self.name
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._backend = None
        self._validate_weights()
        self._load()

    def _weight_candidates(self) -> List[Path]:
        return [
            self.root / "open_clip_pytorch_model.bin",
            self.root / "pytorch_model.bin",
            self.root / "model.safetensors",
            self.root / "config.json",
        ]

    def _validate_weights(self) -> None:
        if not self.root.is_dir():
            raise ModelWeightsMissingError(
                f"CLIP weights directory missing: {self.root}. "
                f"Pre-download openai/clip-vit-base-patch32 into models/{self.name}/ "
                f"while online, then re-run with the network off."
            )
        # Need at least one weight file or a complete HF snapshot
        has_weight = any(
            (self.root / n).exists()
            for n in (
                "pytorch_model.bin",
                "model.safetensors",
                "open_clip_pytorch_model.bin",
                "flax_model.msgpack",
            )
        )
        has_config = (self.root / "config.json").exists()
        if not (has_weight or has_config):
            raise ModelWeightsMissingError(
                f"No CLIP weight files found under {self.root}. "
                f"Place local weights there; offline mode will not download."
            )

    def _load(self) -> None:
        # Prefer open_clip with local checkpoint
        oc_ckpt = self.root / "open_clip_pytorch_model.bin"
        try:
            import open_clip
            import torch

            if oc_ckpt.exists():
                model, _, preprocess = open_clip.create_model_and_transforms(
                    "ViT-B-32", pretrained=None
                )
                state = torch.load(str(oc_ckpt), map_location="cpu")
                model.load_state_dict(state, strict=False)
                model.eval()
                model.to(self.device)
                self._model = model
                self._preprocess = preprocess
                self._tokenizer = open_clip.get_tokenizer("ViT-B-32")
                self._backend = "open_clip"
                logger.info("Loaded CLIP ViT-B/32 via open_clip from %s", oc_ckpt)
                return
        except ModelWeightsMissingError:
            raise
        except Exception as exc:
            logger.info("open_clip path unavailable (%s); trying transformers.", exc)

        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            self._model = CLIPModel.from_pretrained(str(self.root), local_files_only=True)
            self._preprocess = CLIPProcessor.from_pretrained(str(self.root), local_files_only=True)
            self._model.eval()
            self._model.to(self.device)
            self._backend = "transformers"
            logger.info("Loaded CLIP ViT-B/32 via transformers from %s", self.root)
        except Exception as exc:
            raise ModelWeightsMissingError(
                f"Failed to load CLIP from {self.root} (offline): {exc}"
            ) from exc

    def encode_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        from PIL import Image
        import torch

        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        pil_images = []
        for img in images:
            arr = np.asarray(img)
            if arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            if arr.ndim == 2:
                arr = np.stack([arr] * 3, axis=-1)
            pil_images.append(Image.fromarray(arr[..., :3]))

        with torch.no_grad():
            if self._backend == "open_clip":
                tensors = torch.stack([self._preprocess(im) for im in pil_images]).to(self.device)
                feats = self._model.encode_image(tensors)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy().astype(np.float32)
            else:
                inputs = self._preprocess(images=pil_images, return_tensors="pt", padding=True)
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                feats = self._model.get_image_features(**inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy().astype(np.float32)

    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        import torch

        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        with torch.no_grad():
            if self._backend == "open_clip":
                tokens = self._tokenizer(list(texts)).to(self.device)
                feats = self._model.encode_text(tokens)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy().astype(np.float32)
            else:
                inputs = self._preprocess(
                    text=list(texts), return_tensors="pt", padding=True, truncation=True
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                feats = self._model.get_text_features(**inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                return feats.cpu().numpy().astype(np.float32)


class RemoteCLIPModel(EmbeddingModel):
    """
    RemoteCLIP ViT-B-32 via open_clip, weights from models/remoteclip/.
    """

    name = "remoteclip"
    version = "remoteclip-vit-b-32-1.0"
    embedding_dim = 512
    licence = "Apache-2.0"
    source_url = "https://github.com/ChenDelong1999/RemoteCLIP"

    def __init__(self, device: str = "cpu", models_dir: Optional[Path] = None):
        self.device = device
        self.root = Path(models_dir or MODELS_DIR) / self.name
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._validate_weights()
        self._load()

    def _validate_weights(self) -> None:
        ckpt = self.root / "open_clip_pytorch_model.bin"
        if not ckpt.exists():
            # Also accept RemoteCLIP-ViT-B-32.pt style names
            alts = list(self.root.glob("*.pt")) + list(self.root.glob("*.bin"))
            if not alts:
                raise ModelWeightsMissingError(
                    f"RemoteCLIP weights missing under {self.root}. "
                    f"Place open_clip_pytorch_model.bin (or *.pt) there while online; "
                    f"offline mode will not download."
                )

    def _resolve_ckpt(self) -> Path:
        preferred = self.root / "open_clip_pytorch_model.bin"
        if preferred.exists():
            return preferred
        for p in list(self.root.glob("*.pt")) + list(self.root.glob("*.bin")):
            return p
        raise ModelWeightsMissingError(f"No checkpoint in {self.root}")

    def _load(self) -> None:
        import torch
        import open_clip

        ckpt = self._resolve_ckpt()
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained=None
        )
        state = torch.load(str(ckpt), map_location="cpu")
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        # Strip possible module. prefix
        cleaned = {}
        for k, v in state.items():
            cleaned[k.replace("module.", "")] = v
        model.load_state_dict(cleaned, strict=False)
        model.eval()
        model.to(self.device)
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer("ViT-B-32")
        logger.info("Loaded RemoteCLIP from %s", ckpt)

    def encode_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        from PIL import Image
        import torch

        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        pil_images = []
        for img in images:
            arr = np.asarray(img)
            if arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            if arr.ndim == 2:
                arr = np.stack([arr] * 3, axis=-1)
            pil_images.append(Image.fromarray(arr[..., :3]))
        tensors = torch.stack([self._preprocess(im) for im in pil_images]).to(self.device)
        with torch.no_grad():
            feats = self._model.encode_image(tensors)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy().astype(np.float32)

    def encode_text(self, texts: Sequence[str]) -> np.ndarray:
        import torch

        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        tokens = self._tokenizer(list(texts)).to(self.device)
        with torch.no_grad():
            feats = self._model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy().astype(np.float32)


_MODEL_REGISTRY = {
    "clip-vit-base-patch32": CLIPViTB32Model,
    "clip": CLIPViTB32Model,
    "remoteclip": RemoteCLIPModel,
    "fake-hist": FakeEmbeddingModel,
    "fake": FakeEmbeddingModel,
}


def get_embedding_model(
    model_name: str,
    device: str = "cpu",
    models_dir: Optional[Path] = None,
) -> EmbeddingModel:
    key = model_name.strip().lower()
    if key not in _MODEL_REGISTRY:
        raise ValueError(
            f"Unknown embedding model '{model_name}'. "
            f"Choose from: {sorted(set(_MODEL_REGISTRY.keys()))}"
        )
    cls = _MODEL_REGISTRY[key]
    if cls is FakeEmbeddingModel:
        return FakeEmbeddingModel()
    return cls(device=device, models_dir=models_dir)


def write_model_card(model: EmbeddingModel, weight_path: Optional[Path] = None) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    card = model.model_card()
    if weight_path and Path(weight_path).exists():
        card["weight_file"] = str(weight_path)
        card["sha256"] = sha256_file(Path(weight_path))
    else:
        card["sha256"] = None
        card["weight_file"] = None
    # Merge with existing cards
    existing = {}
    if MODEL_CARD_PATH.exists():
        try:
            existing = json.loads(MODEL_CARD_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    if "models" not in existing:
        existing = {"models": existing.get("models", [])} if isinstance(existing, dict) else {"models": []}
        if "name" in (existing if isinstance(existing, dict) else {}):
            existing = {"models": [existing]}
    models_list = existing.get("models", [])
    models_list = [m for m in models_list if m.get("name") != model.name]
    models_list.append(card)
    payload = {"models": models_list, "updated_note": "Declared for offline AerialEye retrieval"}
    MODEL_CARD_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return MODEL_CARD_PATH


def load_model_cards() -> List[dict]:
    if not MODEL_CARD_PATH.exists():
        return []
    try:
        data = json.loads(MODEL_CARD_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "models" in data:
            return data["models"]
        if isinstance(data, list):
            return data
        return [data]
    except Exception:
        return []
