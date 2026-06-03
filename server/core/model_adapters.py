import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Type

import numpy as np
from PIL import Image

try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:  # pragma: no cover
    Interpreter = None

logger = logging.getLogger("pest_robot_server.model_adapters")

DEFAULT_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass",
    "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
    "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


@dataclass
class ModelInfo:
    name: str
    architecture: str
    path: Path
    labels: Sequence[str]
    metadata: Dict[str, Any]


class ModelAdapter(ABC):
    """Base model adapter for inference with pluggable backends."""

    def __init__(self, model_path: Path, labels: Optional[Sequence[str]] = None) -> None:
        self.model_path = model_path
        self.labels = list(labels or DEFAULT_LABELS)
        self.model_name = model_path.stem
        self.architecture = "generic"

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def infer(self, image: Image.Image) -> dict:
        raise NotImplementedError

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self.model_name,
            architecture=self.architecture,
            path=self.model_path,
            labels=self.labels,
            metadata={"format": self.model_path.suffix.lower()},
        )

    def _normalize_boxes(self, boxes: np.ndarray, image_size: int) -> np.ndarray:
        if boxes.ndim == 3 and boxes.shape[0] == 1:
            boxes = boxes[0]
        if boxes.ndim != 2 or boxes.shape[1] != 4:
            raise ValueError("Expected boxes shape [N, 4]")
        boxes = boxes.astype(np.float32)
        x1 = np.clip((boxes[:, 0] - boxes[:, 2] / 2) * image_size, 0, image_size - 1)
        y1 = np.clip((boxes[:, 1] - boxes[:, 3] / 2) * image_size, 0, image_size - 1)
        x2 = np.clip((boxes[:, 0] + boxes[:, 2] / 2) * image_size, 0, image_size - 1)
        y2 = np.clip((boxes[:, 1] + boxes[:, 3] / 2) * image_size, 0, image_size - 1)
        return np.stack([x1, y1, x2, y2], axis=1)

    def _format_detections(
        self,
        boxes: np.ndarray,
        scores: np.ndarray,
        class_indices: Sequence[int],
        min_confidence: float = 0.5,
    ) -> dict:
        if len(boxes) != len(scores) or len(scores) != len(class_indices):
            raise ValueError("Detection output lengths do not match")

        keep = np.array(scores, dtype=np.float32) > min_confidence
        filtered = np.where(keep)[0]

        detections = []
        for idx in filtered:
            label_index = int(class_indices[idx]) if idx < len(class_indices) else 0
            detections.append(
                {
                    "box": boxes[idx].tolist(),
                    "score": float(scores[idx]),
                    "label": self.labels[label_index] if 0 <= label_index < len(self.labels) else str(label_index),
                }
            )
        return {
            "boxes": [d["box"] for d in detections],
            "scores": [d["score"] for d in detections],
            "labels": [d["label"] for d in detections],
        }

    def _preprocess(self, image: Image.Image, target_size: Tuple[int, int] = (640, 640)) -> np.ndarray:
        image = image.convert("RGB").resize(target_size, Image.Resampling.LANCZOS)
        tensor = np.asarray(image, dtype=np.float32) / 255.0
        return tensor


class OnnxModelAdapter(ModelAdapter):
    """ONNX model adapter for RT-DETR-like detection models."""

    def __init__(self, model_path: Path, labels: Optional[Sequence[str]] = None) -> None:
        super().__init__(model_path, labels)
        self.architecture = "onnx"
        self._session = None
        self._input_name = None

    def load(self) -> None:
        import onnxruntime

        session_options = onnxruntime.SessionOptions()
        session_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
        self._session = onnxruntime.InferenceSession(
            str(self.model_path), sess_options=session_options, providers=["CPUExecutionProvider"]
        )
        inputs = self._session.get_inputs()
        if not inputs:
            raise RuntimeError("ONNX model has no inputs")
        self._input_name = inputs[0].name
        logger.info("Loaded ONNX model %s", self.model_path)

    def infer(self, image: Image.Image) -> dict:
        if self._session is None or self._input_name is None:
            raise RuntimeError("ONNX adapter has not been loaded")
        tensor = self._preprocess(image)
        tensor = tensor.transpose(2, 0, 1)[None, ...]
        outputs = self._session.run(None, {self._input_name: tensor})
        return self._parse_outputs(outputs, 640)

    def _parse_outputs(self, outputs: Sequence[Any], image_size: int) -> dict:
        boxes = np.asarray(outputs[0], dtype=np.float32)
        scores = np.asarray(outputs[1], dtype=np.float32)
        class_ids = None
        if len(outputs) >= 3:
            class_ids = np.asarray(outputs[2], dtype=np.int32)

        if boxes.ndim == 3 and boxes.shape[0] == 1:
            boxes = boxes[0]
        if scores.ndim == 3 and scores.shape[0] == 1:
            class_probs = scores[0]
            class_indices = np.argmax(class_probs, axis=-1)
            class_scores = np.max(class_probs, axis=-1)
        elif scores.ndim == 2 and scores.shape[0] == 1:
            class_scores = scores[0]
            class_indices = class_ids[0] if class_ids is not None and class_ids.ndim == 2 else (np.argmax(scores[0], axis=-1) if scores.shape[1] > 1 else np.zeros(scores.shape[1], dtype=np.int32))
        elif scores.ndim == 1:
            class_scores = scores
            class_indices = class_ids if class_ids is not None else np.zeros_like(scores, dtype=np.int32)
        else:
            raise RuntimeError("Unsupported ONNX score tensor shape")

        if class_ids is not None and class_indices.shape != class_scores.shape:
            class_indices = class_indices.reshape(class_scores.shape)

        boxes = self._normalize_boxes(boxes, image_size)
        return self._format_detections(boxes, class_scores, class_indices)


class RFDTROnnxAdapter(OnnxModelAdapter):
    """Adapter for Roboflow RF-DTR ONNX models."""

    def __init__(self, model_path: Path, labels: Optional[Sequence[str]] = None) -> None:
        super().__init__(model_path, labels)
        self.architecture = "rfdtr"

    def infer(self, image: Image.Image) -> dict:
        if self._session is None or self._input_name is None:
            raise RuntimeError("RFDTR adapter has not been loaded")
        tensor = self._preprocess(image)
        tensor = tensor.transpose(2, 0, 1)[None, ...]
        outputs = self._session.run(None, {self._input_name: tensor})
        return self._parse_outputs(outputs, 640)


class TFLiteModelAdapter(ModelAdapter):
    """TFLite adapter for lightweight detection models."""

    def __init__(self, model_path: Path, labels: Optional[Sequence[str]] = None) -> None:
        super().__init__(model_path, labels)
        if Interpreter is None:
            raise RuntimeError("tflite-runtime is required for TFLite model execution")
        self.architecture = "tflite"
        self._interpreter = Interpreter(model_path=str(model_path))
        self._interpreter.allocate_tensors()
        input_details = self._interpreter.get_input_details()[0]
        self._input_index = input_details["index"]
        self._input_shape = tuple(input_details["shape"])
        self._input_dtype = input_details["dtype"]
        self._output_details = self._interpreter.get_output_details()
        logger.info("Loaded TFLite model %s", self.model_path)

    def load(self) -> None:
        # Interpreter is initialized in __init__, we only check its availability here.
        if self._interpreter is None:
            raise RuntimeError("TFLite interpreter initialization failed")

    def infer(self, image: Image.Image) -> dict:
        target_size = (self._input_shape[2], self._input_shape[1]) if len(self._input_shape) == 4 else (640, 640)
        tensor = self._preprocess(image, target_size=target_size)
        if self._input_shape[-1] == 3:
            tensor = tensor.astype(self._input_dtype)
        if len(self._input_shape) == 4:
            tensor = tensor[None, ...]
        if self._input_shape[1] == 3 and self._input_shape[3] == 640:
            tensor = tensor.transpose(0, 3, 1, 2)
        self._interpreter.set_tensor(self._input_index, tensor)
        self._interpreter.invoke()
        outputs = [self._interpreter.get_tensor(output["index"]) for output in self._output_details]
        return self._parse_outputs(outputs, target_size[0])

    def _parse_outputs(self, outputs: Sequence[Any], image_size: int) -> dict:
        boxes = np.asarray(outputs[0], dtype=np.float32)
        scores = np.asarray(outputs[1], dtype=np.float32)
        class_ids = np.asarray(outputs[2], dtype=np.int32) if len(outputs) >= 3 else None
        if boxes.ndim == 3 and boxes.shape[0] == 1:
            boxes = boxes[0]
        if scores.ndim == 2 and scores.shape[0] == 1:
            class_scores = scores[0]
            class_indices = class_ids[0] if class_ids is not None and class_ids.ndim == 2 else np.zeros(scores.shape[1], dtype=np.int32)
        elif scores.ndim == 1:
            class_scores = scores
            class_indices = class_ids if class_ids is not None else np.zeros_like(scores, dtype=np.int32)
        else:
            raise RuntimeError("Unsupported TFLite score tensor shape")
        boxes = self._normalize_boxes(boxes, image_size)
        return self._format_detections(boxes, class_scores, class_indices)


class ModelRegistry:
    """Keeps track of available model adapters and exposes discovery."""

    def __init__(self, model_root: Path) -> None:
        self.model_root = model_root
        self._adapters: Dict[str, ModelAdapter] = {}

    def register(self, name: str, adapter: ModelAdapter) -> None:
        self._adapters[name] = adapter
        logger.info("Registered model %s: %s", name, adapter.architecture)

    def get(self, name: str) -> ModelAdapter:
        if name not in self._adapters:
            raise KeyError(f"Model '{name}' is not registered")
        return self._adapters[name]

    def adapters(self) -> Dict[str, ModelAdapter]:
        return self._adapters

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "architecture": adapter.architecture,
                "path": str(adapter.model_path),
                "metadata": adapter.model_info().metadata,
            }
            for name, adapter in self._adapters.items()
        ]

    def discover(self) -> None:
        if not self.model_root.exists():
            logger.warning("Model root does not exist: %s", self.model_root)
            return
        for model_path in sorted(self.model_root.glob("*.onnx")):
            name = model_path.stem
            adapter_cls = RFDTROnnxAdapter if "rfdtr" in name.lower() else OnnxModelAdapter
            self.register(name, adapter_cls(model_path))
        for model_path in sorted(self.model_root.glob("*.tflite")):
            self.register(model_path.stem, TFLiteModelAdapter(model_path))
