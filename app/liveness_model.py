from __future__ import annotations

import importlib.util
import os
import threading
from typing import Iterable

import cv2
import numpy as np

import config
from . import face_engine

_MODEL_LOCK = threading.Lock()
_MODEL = None
_DEVICE = None
_MODEL_IMPORT_ERROR = None


class DependencyUnavailableError(RuntimeError):
    pass


def pick_frame_indices(candidates: list[int], target_count: int) -> list[int]:
    if not candidates:
        return []
    if len(candidates) <= target_count:
        return list(candidates)
    if target_count <= 1:
        return [candidates[-1]]

    step = (len(candidates) - 1) / float(target_count - 1)
    picked = []
    for offset in range(target_count):
        index = round(offset * step)
        picked.append(candidates[index])
    return picked


def build_skip_result(reason: str, available: bool = False) -> dict:
    return {
        "checked": False,
        "available": available,
        "passed": None,
        "score": None,
        "reason": reason,
        "frame_count": 0,
    }


def build_result_from_scores(scores: Iterable[float], threshold: float) -> dict:
    values = [float(score) for score in scores]
    if not values:
        return build_skip_result("no_face_frames", available=True)

    mean_score = sum(values) / len(values)
    passed = mean_score >= float(threshold)
    return {
        "checked": True,
        "available": True,
        "passed": passed,
        "score": round(mean_score, 4),
        "reason": "passed" if passed else "spoof_detected",
        "frame_count": len(values),
    }


def pick_face_frame_indices(metrics: list) -> list[int]:
    valid = [index for index, metric in enumerate(metrics) if getattr(metric, "has_face", False)]
    return pick_frame_indices(valid, target_count=config.LIVENESS_MODEL_FRAME_COUNT)


def _load_model_module():
    model_path = os.path.join(config.BASE_DIR, "活体检测", "model2", "model.py")
    spec = importlib.util.spec_from_file_location("attendance_liveness_model_impl", model_path)
    if spec is None or spec.loader is None:
        raise DependencyUnavailableError("model_import_failed")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ensure_model():
    global _MODEL, _DEVICE, _MODEL_IMPORT_ERROR
    if _MODEL is not None:
        return _MODEL, _DEVICE
    if _MODEL_IMPORT_ERROR is not None:
        raise DependencyUnavailableError(_MODEL_IMPORT_ERROR)

    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL, _DEVICE
        if _MODEL_IMPORT_ERROR is not None:
            raise DependencyUnavailableError(_MODEL_IMPORT_ERROR)

        try:
            import torch
        except Exception:
            _MODEL_IMPORT_ERROR = "dependency_missing"
            raise DependencyUnavailableError(_MODEL_IMPORT_ERROR)

        if not os.path.exists(config.LIVENESS_MODEL_PATH):
            _MODEL_IMPORT_ERROR = "weight_missing"
            raise DependencyUnavailableError(_MODEL_IMPORT_ERROR)

        try:
            module = _load_model_module()
            model = module.EfficientNetDetector(pretrained=False)
            checkpoint = torch.load(config.LIVENESS_MODEL_PATH, map_location="cpu", weights_only=False)
            state_dict = checkpoint.get("model_state", checkpoint)
            model.load_state_dict(state_dict, strict=False)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)
            model.eval()
        except DependencyUnavailableError:
            raise
        except Exception:
            _MODEL_IMPORT_ERROR = "model_load_failed"
            raise DependencyUnavailableError(_MODEL_IMPORT_ERROR)

        _MODEL = model
        _DEVICE = device
        return _MODEL, _DEVICE


def _prepare_face_tensor(face_bgr: np.ndarray):
    try:
        import torch
    except Exception as exc:
        raise DependencyUnavailableError("dependency_missing") from exc

    rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(
        rgb,
        (config.LIVENESS_MODEL_INPUT_SIZE, config.LIVENESS_MODEL_INPUT_SIZE),
        interpolation=cv2.INTER_LINEAR,
    )
    tensor = torch.from_numpy(resized.transpose(2, 0, 1)).float() / 255.0
    mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    tensor = (tensor - mean) / std
    return tensor.unsqueeze(0)


def score_frame(frame) -> float:
    if frame is None:
        raise DependencyUnavailableError("invalid_frame")

    model, device = _ensure_model()
    face_boxes = face_engine.detect_faces(frame, upsample=1)
    if not face_boxes:
        raise DependencyUnavailableError("no_face_detected")

    biggest = max(face_boxes, key=lambda rect: rect.width() * rect.height())
    face_roi = face_engine.crop_face(frame, biggest, margin=config.LIVENESS_MODEL_FACE_MARGIN)
    if face_roi.size == 0:
        raise DependencyUnavailableError("empty_face_crop")

    tensor = _prepare_face_tensor(face_roi)

    import torch

    with torch.no_grad():
        logits = model(tensor.to(device))
        score = torch.sigmoid(logits).detach().cpu().item()
    return float(score)


def verify_liveness_from_frames(decoded_frames: list, metrics: list) -> dict:
    indices = pick_face_frame_indices(metrics)
    if not indices:
        return build_skip_result("no_face_frames", available=True)

    try:
        scores = [score_frame(decoded_frames[index]) for index in indices]
    except DependencyUnavailableError as exc:
        if not config.LIVENESS_MODEL_ALLOW_SKIP:
            return {
                "checked": True,
                "available": False,
                "passed": False,
                "score": 0.0,
                "reason": str(exc),
                "frame_count": 0,
            }
        return build_skip_result(str(exc), available=False)
    except Exception:
        if not config.LIVENESS_MODEL_ALLOW_SKIP:
            return {
                "checked": True,
                "available": False,
                "passed": False,
                "score": 0.0,
                "reason": "inference_failed",
                "frame_count": 0,
            }
        return build_skip_result("inference_failed", available=False)

    return build_result_from_scores(scores, threshold=config.LIVENESS_MODEL_THRESHOLD)
