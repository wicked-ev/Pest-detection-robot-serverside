import json
import logging
import os
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

try:
    from rfdetr import RFDETRNano
except ImportError:  # pragma: no cover
    RFDETRNano = None

try:
    import supervision as sv
except ImportError:  # pragma: no cover
    sv = None

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

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


def load_dataset_classes(annotations_path: str) -> dict[int, str]:
    """
    Load class ID → class name mapping from a COCO-format annotations file.
    Roboflow exports categories sorted by ID, but we sort explicitly to be safe.
    """
    if not annotations_path or not os.path.exists(annotations_path):
        raise FileNotFoundError(f"Annotations file not found: {annotations_path}")

    decode_attempts = ["utf-8", "utf-8-sig", "cp1252"]
    last_error = None
    for encoding in decode_attempts:
        try:
            with open(annotations_path, "r", encoding=encoding) as f:
                coco = json.load(f)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    else:
        raise UnicodeDecodeError(
            "Unable to decode annotations file. Tried utf-8, utf-8-sig, and cp1252.",
            *last_error.args,
        ) from last_error

    if "categories" not in coco:
        raise KeyError("No 'categories' key found in annotations file — is this a valid COCO JSON?")

    # Build {id: name} dict sorted by ID so index lookups are always correct
    return {cat["id"]: cat["name"] for cat in sorted(coco["categories"], key=lambda c: c["id"])}



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


class RFDETRNanoAdapter(ModelAdapter):
    """Adapter for Roboflow RF-DETR Nano models using rfdetr library."""

    def __init__(self, model_path: Path, labels: Optional[Sequence[str]] = None) -> None:
        super().__init__(model_path, labels)
        if RFDETRNano is None:
            raise RuntimeError("rfdetr package is required for RF-DETR Nano model execution")
        self.architecture = "rfdtr_nano"
        self._model = None

    def load(self) -> None:
        """Load RF-DETR Nano model."""
        if RFDETRNano is None:
            raise RuntimeError("rfdetr is not installed")
        
        try:
            self._model = RFDETRNano()
            logger.info("Loaded RF-DETR Nano model")
        except Exception as e:
            logger.error("Failed to load RF-DETR Nano model: %s", e)
            raise

    def infer(self, image: Image.Image) -> dict:
        """Run inference using RF-DETR Nano model."""
        if self._model is None:
            raise RuntimeError("RF-DETR Nano adapter has not been loaded")
        
        try:
            if cv2 is None:
                raise RuntimeError("cv2 is not installed")
            
            # Convert PIL image to RGB numpy array
            image_rgb = np.array(image.convert("RGB"))
            
            # Run inference with threshold
            detections = self._model.predict(image_rgb, threshold=0.5)
            
            return self._parse_detections(detections)
        except Exception as e:
            logger.error("RF-DETR Nano inference failed: %s", e)
            raise

    def _parse_detections(self, detections: Any) -> dict:
        """Parse RF-DETR Nano detections into standard format."""
        try:
            boxes = []
            scores = []
            labels = []
            
            # RF-DETR returns detections with class_id and confidence attributes
            if hasattr(detections, "xyxy"):
                # Standard supervision format: xyxy box format
                for i, (box, class_id, conf) in enumerate(
                    zip(detections.xyxy, detections.class_id, detections.confidence)
                ):
                    boxes.append(box.tolist() if hasattr(box, "tolist") else list(box))
                    scores.append(float(conf))
                    # Map class_id to label
                    label_index = int(class_id) if class_id is not None else 0
                    if 0 <= label_index < len(self.labels):
                        labels.append(self.labels[label_index])
                    else:
                        labels.append(str(label_index))
            
            return {
                "boxes": boxes,
                "scores": scores,
                "labels": labels,
            }
        except Exception as e:
            logger.error("Failed to parse RF-DETR detections: %s", e)
            raise
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
        
        # Look for COCO annotations file
        coco_annotations = None
        for ann_file in self.model_root.glob("*_annotations.coco.json"):
            coco_annotations = ann_file
            break
        
        # Load labels from COCO annotations if available
        labels = None
        if coco_annotations:
            try:
                class_dict = load_dataset_classes(str(coco_annotations))
                # Convert {id: name} dict to a list indexed by id
                max_id = max(class_dict.keys()) if class_dict else 0
                labels = [""] * (max_id + 1)
                for class_id, class_name in class_dict.items():
                    labels[class_id] = class_name
                logger.info("Loaded %d classes from COCO annotations: %s", len(labels), coco_annotations)
            except Exception as e:
                logger.warning("Failed to load COCO annotations from %s: %s", coco_annotations, e)
                labels = None
        
        # Discover ONNX models
        for model_path in sorted(self.model_root.glob("*.onnx")):
            name = model_path.stem
            adapter_cls = RFDTROnnxAdapter if "rfdtr" in name.lower() else OnnxModelAdapter
            self.register(name, adapter_cls(model_path, labels=labels or None))
        
        # Discover TFLite models
        for model_path in sorted(self.model_root.glob("*.tflite")):
            self.register(model_path.stem, TFLiteModelAdapter(model_path, labels=labels or None))
        
        # Discover RF-DETR Nano models (.pt files)
        for model_path in sorted(self.model_root.glob("*.pt")):
            name = model_path.stem
            self.register(name, RFDETRNanoAdapter(model_path, labels=labels or None))
