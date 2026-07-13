"""EfficientNet orientation classifier for auto-rotation keyframe analysis."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageOps

if TYPE_CHECKING:
    import onnxruntime as ort

logger = logging.getLogger(__name__)

IMAGE_SIZE = 384
RESIZE_SIZE = IMAGE_SIZE + 32
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Model outputs corrective rotation: 0°, 90° CW, 180°, 270° (90° CCW).
_CLASS_LABELS = {
    0: "correctly oriented (0°)",
    1: "rotate 90° clockwise",
    2: "rotate 180°",
    3: "rotate 90° counter-clockwise",
}


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


def load_image_rgb(path: Path) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGB", "L"):
            return img.convert("RGB")
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background


def preprocess_image(path: Path) -> np.ndarray:
    """Return NCHW float32 tensor matching the training pipeline."""
    image = load_image_rgb(path)
    resized = image.resize((RESIZE_SIZE, RESIZE_SIZE), Image.Resampling.BILINEAR)
    offset = (RESIZE_SIZE - IMAGE_SIZE) // 2
    cropped = resized.crop(
        (offset, offset, offset + IMAGE_SIZE, offset + IMAGE_SIZE)
    )
    array = np.asarray(cropped, dtype=np.float32) / 255.0
    array = (array - _IMAGENET_MEAN) / _IMAGENET_STD
    return np.transpose(array, (2, 0, 1))[np.newaxis, ...]


def resolve_model_path(
    *,
    repo_id: str,
    filename: str,
    cache_dir: Path | None = None,
) -> Path:
    from huggingface_hub import hf_hub_download

    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir=str(cache_dir) if cache_dir is not None else None,
    )
    return Path(downloaded)


@lru_cache(maxsize=4)
def _load_session(model_path: str) -> ort.InferenceSession:
    import onnxruntime as ort

    preferred = [
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ]
    available = set(ort.get_available_providers())
    providers = [provider for provider in preferred if provider in available]
    if not providers:
        providers = ["CPUExecutionProvider"]
    session = ort.InferenceSession(model_path, providers=providers)
    logger.info(
        "Loaded orientation ONNX model from %s using %s",
        model_path,
        session.get_providers()[0],
    )
    return session


def predict_orientation(
    image_path: Path,
    *,
    repo_id: str,
    model_filename: str,
    cache_dir: Path | None = None,
    min_confidence: float = 0.55,
) -> tuple[int, float] | None:
    """Return (class_index, confidence) or None when below threshold / on failure."""
    try:
        model_path = resolve_model_path(
            repo_id=repo_id,
            filename=model_filename,
            cache_dir=cache_dir,
        )
        session = _load_session(str(model_path))
        input_name = session.get_inputs()[0].name
        logits = session.run(None, {input_name: preprocess_image(image_path)})[0]
        probabilities = _softmax(np.asarray(logits, dtype=np.float32))[0]
        class_index = int(np.argmax(probabilities))
        confidence = float(probabilities[class_index])
    except Exception as exc:
        logger.warning("Orientation classifier failed for %s: %s", image_path, exc)
        return None

    if confidence < min_confidence:
        return None
    return class_index, confidence


def class_index_to_degrees(class_index: int) -> int:
    return {0: 0, 1: 90, 2: 180, 3: 270}.get(class_index, 0)


def class_label(class_index: int) -> str:
    return _CLASS_LABELS.get(class_index, f"unknown class {class_index}")
