"""全局配置"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask
SECRET_KEY = "change-me-in-production-please"
UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
STUDENTS_FOLDER = os.path.join(UPLOAD_FOLDER, "students")
ACTIVITIES_FOLDER = os.path.join(UPLOAD_FOLDER, "activities")
ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "bmp"}
MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB

# 数据库
DB_PATH = os.path.join(BASE_DIR, "data", "attendance.db")

# 模型文件（需提前下载到项目根目录）
SHAPE_PREDICTOR_PATH = os.path.join(BASE_DIR, "shape_predictor_68_face_landmarks.dat")
FACE_REC_MODEL_PATH = os.path.join(BASE_DIR, "dlib_face_recognition_resnet_model_v1.dat")

# 人脸识别阈值（128维欧氏距离，0.6 是 dlib 官方推荐）
FACE_MATCH_THRESHOLD = 0.5

# 活体检测参数
EAR_BLINK_THRESHOLD = 0.21       # 眼睛闭合的 EAR 阈值
EAR_OPEN_THRESHOLD = 0.27        # 眼睛恢复睁开的阈值
MAR_OPEN_THRESHOLD = 0.55        # 嘴巴张开的 MAR 阈值
HEAD_YAW_THRESHOLD = 18.0        # 转头偏航角阈值（度）
LIVENESS_FRAME_MIN = 8           # 最少帧数
LIVENESS_FRAME_MAX = 60          # 最多帧数

# 情绪类型映射（DeepFace 的英文 → 中文）
EMOTION_CN = {
    "angry": "愤怒", "disgust": "厌恶", "fear": "恐惧",
    "happy": "高兴", "sad": "悲伤", "surprise": "惊讶", "neutral": "中性",
}
