"""Tests for the orientation classifier wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from viral_editor.video.orientation_classifier import (
    class_index_to_degrees,
    class_label,
    preprocess_image,
)


def test_class_index_to_degrees_maps_model_classes() -> None:
    assert class_index_to_degrees(0) == 0
    assert class_index_to_degrees(1) == 90
    assert class_index_to_degrees(2) == 180
    assert class_index_to_degrees(3) == 270


def test_preprocess_image_returns_nchw_tensor(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (640, 480), color=(120, 80, 40)).save(image_path, format="JPEG")

    tensor = preprocess_image(image_path)

    assert tensor.shape == (1, 3, 384, 384)
    assert tensor.dtype == np.float32


def test_class_label_describes_correction() -> None:
    assert "clockwise" in class_label(1).lower()
    assert "counter-clockwise" in class_label(3).lower()
