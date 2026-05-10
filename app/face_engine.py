"""人脸识别核心模块：检测、关键点、128 维特征编码、相似度比对、情绪识别。

设计要点：
1. dlib 模型只加载一次（首次调用时懒加载），避免每次请求都重新加载。
2. encoding 用 numpy float32 存储到 SQLite（BLOB），便于反序列化为向量。
3. 情绪识别使用 DeepFace；如未安装或失败，降级返回 unknown。
"""
from __future__ import annotations

import io
import os
import threading
from typing import List, Optional, Tuple

import cv2
import dlib
import numpy as np

import config

# -----------------------------------------------------------------------------
# 模型懒加载
# -----------------------------------------------------------------------------
_lock = threading.Lock()
_detector = None
_predictor = None
_recognizer = None
_deepface_loaded = False
_enhancer = None


def _ensure_models():
    """惰性加载 dlib 模型（首次调用阻塞，后续直接返回）。"""
    global _detector, _predictor, _recognizer, _enhancer
    if _detector is not None:
        return
    with _lock:
        if _detector is not None:
            return
        if not os.path.exists(config.SHAPE_PREDICTOR_PATH):
            raise FileNotFoundError(
                f"缺少模型文件 {config.SHAPE_PREDICTOR_PATH}，"
                "请下载 shape_predictor_68_face_landmarks.dat 放到项目根目录"
            )
        if not os.path.exists(config.FACE_REC_MODEL_PATH):
            raise FileNotFoundError(
                f"缺少模型文件 {config.FACE_REC_MODEL_PATH}，"
                "请下载 dlib_face_recognition_resnet_model_v1.dat 放到项目根目录"
            )
        _detector = dlib.get_frontal_face_detector()
        _predictor = dlib.shape_predictor(config.SHAPE_PREDICTOR_PATH)
        _recognizer = dlib.face_recognition_model_v1(config.FACE_REC_MODEL_PATH)
        
        if _enhancer is None:
            from .face_enhancer import FaceEnhancer
            _enhancer = FaceEnhancer(upscale=2)


def get_detector():
    _ensure_models()
    return _detector


def get_predictor():
    _ensure_models()
    return _predictor


# -----------------------------------------------------------------------------
# 工具：图像 IO
# -----------------------------------------------------------------------------
def decode_image(buf: bytes) -> Optional[np.ndarray]:
    """从原始字节解码为 BGR ndarray。"""
    arr = np.frombuffer(buf, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def decode_dataurl(data_url: str) -> Optional[np.ndarray]:
    """前端 canvas.toDataURL("image/jpeg") 字符串 → BGR ndarray。"""
    if not data_url:
        return None
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    import base64
    try:
        return decode_image(base64.b64decode(data_url))
    except Exception:
        return None


# -----------------------------------------------------------------------------
# 检测 + 编码
# -----------------------------------------------------------------------------
def detect_faces(img_bgr: np.ndarray, upsample: int = 1) -> List[dlib.rectangle]:
    """返回 dlib.rectangle 列表。upsample 越大越能检测小脸（合照建议 1-2）。"""
    _ensure_models()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return list(_detector(rgb, upsample))


def encode_face(img_bgr: np.ndarray, face: dlib.rectangle) -> np.ndarray:
    """计算单张脸的 128 维 embedding（float32）。"""
    _ensure_models()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    shape = _predictor(rgb, face)
    desc = _recognizer.compute_face_descriptor(rgb, shape, num_jitters=1)
    return np.array(desc, dtype=np.float32)

def encode_face_with_enhancement(img_bgr: np.ndarray, face: dlib.rectangle, min_size: int = 120) -> np.ndarray:
    """
    带超分的人脸特征提取。
    min_size: 如果人脸宽高小于此像素，则触发超分。
    """
    _ensure_models()
    
    # 1. 判断人脸尺寸，决定是否需要超分
    w, h = face.width(), face.height()
    if w >= min_size and h >= min_size:
        # 人脸够大，直接用原来的方式提取
        return encode_face(img_bgr, face)
    
    # 2. 人脸太小/模糊，进行裁剪和超分
    # 使用自带的 crop_face 函数，给一点 margin 帮助模型获取上下文
    cropped_face = crop_face(img_bgr, face, margin=20) 
    
    # 执行超分
    high_res_face = _enhancer.enhance(cropped_face)
    
    # 3. 对超分后的新图片提取特征
    # 因为图片变了，我们需要构造一个新的 dlib.rectangle，框住整张新图片
    hr_h, hr_w = high_res_face.shape[:2]
    new_face_rect = dlib.rectangle(0, 0, hr_w, hr_h)
    
    # 转为 RGB 送入 dlib
    rgb_hr = cv2.cvtColor(high_res_face, cv2.COLOR_BGR2RGB)
    
    # 重新获取关键点并计算 128 维特征
    shape = _predictor(rgb_hr, new_face_rect)
    desc = _recognizer.compute_face_descriptor(rgb_hr, shape, num_jitters=1)
    
    return np.array(desc, dtype=np.float32)

def encode_first_face(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    faces = detect_faces(img_bgr, upsample=1)
    if not faces:
        return None
    # 取面积最大的人脸（注册照通常是单人特写）
    biggest = max(faces, key=lambda r: r.width() * r.height())
    return encode_face(img_bgr, biggest)


def encoding_to_blob(enc: np.ndarray) -> bytes:
    return enc.astype(np.float32).tobytes()


def blob_to_encoding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


# -----------------------------------------------------------------------------
# 比对
# -----------------------------------------------------------------------------
def match_one(query_enc: np.ndarray, gallery: List[Tuple[int, np.ndarray]],
              threshold: float = None) -> Tuple[Optional[int], float]:
    """1:N 匹配。返回 (匹配到的 student_id 或 None, 最近距离)。"""
    if threshold is None:
        threshold = config.FACE_MATCH_THRESHOLD
    if not gallery:
        return None, float("inf")
    encs = np.stack([e for _, e in gallery])
    diffs = np.linalg.norm(encs - query_enc, axis=1)
    idx = int(np.argmin(diffs))
    best = float(diffs[idx])
    if best <= threshold:
        return gallery[idx][0], best
    return None, best


# -----------------------------------------------------------------------------
# 情绪识别（DeepFace 封装）
# -----------------------------------------------------------------------------
def analyze_emotion(face_bgr: np.ndarray) -> str:
    """对裁切好的人脸 ROI 做情绪分析。失败返回 'unknown'。"""
    global _deepface_loaded
    try:
        from deepface import DeepFace  # noqa: WPS433
    except Exception:
        return "unknown"
    try:
        result = DeepFace.analyze(
            face_bgr,
            actions=["emotion"],
            enforce_detection=False,
            detector_backend="skip",   # 已经裁切过
            silent=True,
        )
        if isinstance(result, list):
            result = result[0]
        emo_dict = result.get("emotion", {})
        if not emo_dict:
            return "unknown"
        return max(emo_dict, key=emo_dict.get)
    except Exception:
        return "unknown"


def crop_face(img_bgr: np.ndarray, face: dlib.rectangle, margin: int = 12) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    x1 = max(0, face.left() - margin)
    y1 = max(0, face.top() - margin)
    x2 = min(w, face.right() + margin)
    y2 = min(h, face.bottom() + margin)
    return img_bgr[y1:y2, x1:x2].copy()
