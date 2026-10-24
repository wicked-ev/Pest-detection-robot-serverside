"""Label mapping, model discovery and RF-DETR checkpoint loading."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

import core.model_adapters as model_adapters
from core.model_adapters import ModelRegistry, RFDETRNanoAdapter, load_dataset_classes

# Shaped like the Roboflow export: id 0 is the parent category, real classes start at 1.
CATEGORIES = [
    {"id": 0, "name": "Thrips-Bugs-Pest-helicoverpa", "supercategory": "none"},
    {"id": 1, "name": "Africanized Honey Bees -Killer Bees-", "supercategory": "Thrips-Bugs-Pest-helicoverpa"},
    {"id": 2, "name": "whitefly", "supercategory": "Thrips-Bugs-Pest-helicoverpa"},
]


@pytest.fixture
def models_dir(tmp_path) -> Path:
    (tmp_path / "_annotations.coco.json").write_text(json.dumps({"categories": CATEGORIES}))
    (tmp_path / "pest_model.pt").write_bytes(b"")  # discovery only looks at the name
    return tmp_path


def test_classes_are_keyed_by_category_id(models_dir):
    classes = load_dataset_classes(str(models_dir / "_annotations.coco.json"))
    assert classes[1] == "Africanized Honey Bees -Killer Bees-"
    assert classes[2] == "whitefly"


def test_discovery_registers_pt_models_with_annotation_labels(models_dir):
    registry = ModelRegistry(models_dir)
    registry.discover()
    adapter = registry.get("pest_model")
    assert isinstance(adapter, RFDETRNanoAdapter)
    assert adapter.labels == [c["name"] for c in CATEGORIES]


def test_class_ids_map_to_the_right_pest_names(models_dir):
    # RF-DETR reports the dataset's category id, so id 2 must be "whitefly", not the next class over.
    registry = ModelRegistry(models_dir)
    registry.discover()
    adapter = registry.get("pest_model")
    detections = SimpleNamespace(
        xyxy=np.array([[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]]),
        class_id=np.array([2, 1]),
        confidence=np.array([0.8, 0.6]),
    )
    result = adapter._parse_detections(detections)
    assert result["labels"] == ["whitefly", "Africanized Honey Bees -Killer Bees-"]
    assert result["boxes"] == [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]]
    assert result["scores"] == pytest.approx([0.8, 0.6])


def test_load_uses_the_checkpoint_file_and_its_training_resolution(tmp_path, monkeypatch):
    import torch

    checkpoint = tmp_path / "pest_model.pt"
    torch.save({"args": argparse.Namespace(resolution=640), "model": {}}, checkpoint)

    created = {}

    class FakeRFDETRNano:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def optimize_for_inference(self):
            pass

    monkeypatch.setattr(model_adapters, "RFDETRNano", FakeRFDETRNano)
    adapter = RFDETRNanoAdapter(checkpoint)
    adapter.load()

    # Without pretrain_weights the library silently loads its generic COCO model.
    assert created == {"pretrain_weights": str(checkpoint), "resolution": 640}
    assert adapter.is_loaded()


REAL_MODEL = Path(__file__).resolve().parent.parent / "models" / "pest_model.pt"


@pytest.mark.slow
@pytest.mark.skipif(not REAL_MODEL.exists(), reason="models/pest_model.pt is not present")
def test_real_model_loads_and_finds_nothing_in_a_blank_image():
    registry = ModelRegistry(REAL_MODEL.parent)
    registry.discover()
    adapter = registry.get("pest_model")
    adapter.load()
    result = adapter.infer(Image.new("RGB", (640, 480), (90, 120, 60)))
    assert result == {"boxes": [], "scores": [], "labels": []}
    assert adapter.labels[24] == "whitefly"
