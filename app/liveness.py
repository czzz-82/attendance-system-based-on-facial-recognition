"""动作活体检测：基于 dlib 68 关键点 + solvePnP 头部姿态。

抗攻击思路：
- 服务端在每次会话生成随机 1~2 个动作（眨眼 / 张嘴 / 左转 / 右转）。
- 前端连续采样多帧，编码后整体上传；
- 服务端在帧序列上跑状态机，必须看到完整动作过程才判通过。
- 由于挑战是随机的、动作必须在限定时间窗内完成，单张照片 / 重放视频均无法通过。
"""
from __future__ import annotations

import math
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

import config
from . import face_engine

# -----------------------------------------------------------------------------
# 关键点工具
# -----------------------------------------------------------------------------
LEFT_EYE = list(range(36, 42))
RIGHT_EYE = list(range(42, 48))
MOUTH_OUTER = list(range(48, 60))
MOUTH_INNER = list(range(60, 68))


def _euclid(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def eye_aspect_ratio(pts: np.ndarray, idxs: List[int]) -> float:
    p = [pts[i] for i in idxs]
    A = _euclid(p[1], p[5])
    B = _euclid(p[2], p[4])
    C = _euclid(p[0], p[3])
    return (A + B) / (2.0 * C + 1e-6)


def mouth_aspect_ratio(pts: np.ndarray) -> float:
    """张嘴比例：内唇上下距离 / 嘴宽。"""
    top = pts[62]
    bot = pts[66]
    left = pts[60]
    right = pts[64]
    return _euclid(top, bot) / (_euclid(left, right) + 1e-6)


# -----------------------------------------------------------------------------
# 头部姿态（solvePnP）
# -----------------------------------------------------------------------------
# 通用 3D 模型点（毫米）
_MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),             # 鼻尖 30
    (0.0, -330.0, -65.0),        # 下巴 8
    (-225.0, 170.0, -135.0),     # 左眼外角 36
    (225.0, 170.0, -135.0),      # 右眼外角 45
    (-150.0, -150.0, -125.0),    # 左嘴角 48
    (150.0, -150.0, -125.0),     # 右嘴角 54
], dtype=np.float64)

_PNP_IDS = [30, 8, 36, 45, 48, 54]


def head_pose_yaw(pts: np.ndarray, img_w: int, img_h: int) -> Optional[float]:
    """返回 yaw（左右转头），单位：度。失败返回 None。"""
    image_points = np.array([pts[i] for i in _PNP_IDS], dtype=np.float64)
    focal = img_w
    center = (img_w / 2, img_h / 2)
    cam = np.array([[focal, 0, center[0]],
                    [0, focal, center[1]],
                    [0, 0, 1]], dtype=np.float64)
    dist = np.zeros((4, 1))
    ok, rvec, tvec = cv2.solvePnP(_MODEL_POINTS, image_points, cam, dist,
                                  flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    rot, _ = cv2.Rodrigues(rvec)
    sy = math.sqrt(rot[0, 0] ** 2 + rot[1, 0] ** 2)
    if sy < 1e-6:
        return None
    yaw = math.degrees(math.atan2(-rot[2, 0], sy))
    return yaw


# -----------------------------------------------------------------------------
# 单帧关键点测量
# -----------------------------------------------------------------------------
@dataclass
class FrameMetric:
    has_face: bool
    ear: float = 0.0
    mar: float = 0.0
    yaw: float = 0.0
    box: Optional[Tuple[int, int, int, int]] = None  # x,y,w,h


def measure_frame(img_bgr: np.ndarray) -> FrameMetric:
    detector = face_engine.get_detector()
    predictor = face_engine.get_predictor()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    faces = detector(rgb, 0)
    if not faces:
        return FrameMetric(False)
    face = max(faces, key=lambda r: r.width() * r.height())
    shape = predictor(rgb, face)
    pts = np.array([[shape.part(i).x, shape.part(i).y] for i in range(68)], dtype=np.float32)
    ear_l = eye_aspect_ratio(pts, LEFT_EYE)
    ear_r = eye_aspect_ratio(pts, RIGHT_EYE)
    ear = (ear_l + ear_r) / 2.0
    mar = mouth_aspect_ratio(pts)
    yaw = head_pose_yaw(pts, img_bgr.shape[1], img_bgr.shape[0]) or 0.0
    box = (face.left(), face.top(), face.width(), face.height())
    return FrameMetric(True, ear, mar, yaw, box)


# -----------------------------------------------------------------------------
# 动作判定（在帧序列上）
# -----------------------------------------------------------------------------
ACTIONS = {
    "blink": "请眨一次眼睛",
    "open_mouth": "请张开嘴巴",
    "turn_left": "请向左转头",
    "turn_right": "请向右转头",
}


def random_challenges(n: int = 2) -> List[str]:
    keys = list(ACTIONS.keys())
    return random.sample(keys, n)


def verify_action(action: str, frames: List[FrameMetric]) -> bool:
    """在帧序列上检查指定动作是否完成。"""
    valid = [f for f in frames if f.has_face]
    if len(valid) < config.LIVENESS_FRAME_MIN:
        return False

    if action == "blink":
        # EAR 出现一次「先低于闭合阈值，再回到睁开阈值」
        seen_close = False
        for f in valid:
            if f.ear < config.EAR_BLINK_THRESHOLD:
                seen_close = True
            elif seen_close and f.ear > config.EAR_OPEN_THRESHOLD:
                return True
        return False

    if action == "open_mouth":
        peak = max(f.mar for f in valid)
        base = min(f.mar for f in valid)
        return peak > config.MAR_OPEN_THRESHOLD and (peak - base) > 0.15

    if action == "turn_left":
        # 摄像头镜像后，"向左转头" 表现为 yaw 趋向负值
        return min(f.yaw for f in valid) < -config.HEAD_YAW_THRESHOLD

    if action == "turn_right":
        return max(f.yaw for f in valid) > config.HEAD_YAW_THRESHOLD

    return False


# -----------------------------------------------------------------------------
# 会话管理
# -----------------------------------------------------------------------------
@dataclass
class LivenessSession:
    token: str
    challenges: List[str]
    created_at: float = field(default_factory=time.time)
    used: bool = False


_SESSIONS: Dict[str, LivenessSession] = {}
_SESSION_TTL = 120  # 秒


def create_session(n: int = 2) -> LivenessSession:
    _gc_sessions()
    token = secrets.token_urlsafe(16)
    sess = LivenessSession(token=token, challenges=random_challenges(n))
    _SESSIONS[token] = sess
    return sess


def get_session(token: str) -> Optional[LivenessSession]:
    _gc_sessions()
    return _SESSIONS.get(token)


def consume_session(token: str):
    sess = _SESSIONS.pop(token, None)
    if sess:
        sess.used = True


def _gc_sessions():
    now = time.time()
    expired = [k for k, v in _SESSIONS.items() if now - v.created_at > _SESSION_TTL]
    for k in expired:
        _SESSIONS.pop(k, None)
