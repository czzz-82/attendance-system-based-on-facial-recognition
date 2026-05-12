# 代码文件功能概述

本文档介绍基于人脸识别的考勤系统的各个代码文件的功能和主要函数。

## 根目录文件

### config.py
**功能**：全局配置文件，定义路径、阈值、模型文件位置等常量。

**主要内容**：
- Flask 配置（SECRET_KEY, UPLOAD_FOLDER 等）
- 数据库路径
- 模型文件路径（dlib 模型、GFPGAN、活体检测模型）
- 人脸识别阈值（FACE_MATCH_THRESHOLD = 0.4）
- 活体检测参数（EAR 阈值、帧数等）
- 情绪类型映射

### manage.py
**功能**：命令行工具，用于数据库初始化和用户管理。

**主要函数**：
- `adduser(username, password, role, student_id=None)`：添加或更新用户账号
- `main()`：命令行入口，处理 initdb 和 adduser 命令

### run.py
**功能**：Flask 应用启动入口。

**主要内容**：
- 创建 Flask 应用实例
- 启动开发服务器（host="127.0.0.1", port=5000）

### sitecustomize.py
**功能**：Python 启动时自定义配置（可能为空或用于调试）。

## app/ 目录

### __init__.py
**功能**：Flask 应用工厂函数，注册蓝图和初始化组件。

**主要函数**：
- `create_app() -> Flask`：创建并配置 Flask 应用，注册所有路由蓝图

### auth.py
**功能**：用户认证和权限管理模块。

**主要函数**：
- `hash_password(pw: str) -> str`：密码哈希
- `verify_password(stored: str, pw: str) -> bool`：密码验证
- `login_user(user: dict)`：用户登录会话
- `logout_user()`：用户登出
- `current_user()`：获取当前用户
- `login_required(view)`：登录要求装饰器
- `teacher_required(view)`：教师权限装饰器
- `ensure_default_admin()`：确保默认管理员账号存在

### face_engine.py
**功能**：人脸识别核心模块，包含检测、编码、比对、情绪识别等。

**主要函数**：
- `_ensure_models()`：惰性加载 dlib 模型
- `get_detector()`：获取人脸检测器
- `get_predictor()`：获取关键点预测器
- `decode_image(buf: bytes)`：字节解码为图像
- `decode_dataurl(data_url: str)`：DataURL 解码为图像
- `detect_faces(img_bgr: np.ndarray, upsample: int = 1)`：检测人脸
- `encode_face(img_bgr: np.ndarray, face: dlib.rectangle)`：单脸特征编码
- `encode_face_with_enhancement(img_bgr: np.ndarray, face: dlib.rectangle, min_size: int = 120)`：带超分的人脸编码
- `enhance_face_image(face_img_bgr: np.ndarray)`：人脸超分增强
- `encode_first_face(img_bgr: np.ndarray)`：编码第一张人脸
- `encoding_to_blob(enc: np.ndarray) -> bytes`：编码转字节
- `blob_to_encoding(blob: bytes) -> np.ndarray`：字节转编码
- `match_one(query_enc: np.ndarray, gallery: List[Tuple[int, np.ndarray]], threshold: float = None)`：1:N 匹配
- `analyze_emotion(face_bgr: np.ndarray) -> str`：情绪分析
- `crop_face(img_bgr: np.ndarray, face: dlib.rectangle, margin: int = 12)`：裁剪人脸

### face_enhancer.py
**功能**：人脸超分辨率模块，使用 GFPGAN 模型。

**主要类/函数**：
- `FaceEnhancer` 类：超分增强器
  - `__init__(self, upscale: int = 2)`：初始化 GFPGAN 模型
  - `enhance(self, img: np.ndarray) -> np.ndarray`：执行超分

### liveness_model.py
**功能**：活体检测模型封装。

**主要类/函数**：
- `LivenessModel` 类：活体检测模型
  - `__init__(self, model_path: str, input_size: int = 256, frame_count: int = 5)`：初始化模型
  - `predict(self, frames: List[np.ndarray]) -> float`：预测活体分数

### liveness.py
**功能**：活体检测逻辑，包含眨眼、转头、张嘴检测。

**主要函数**：
- `detect_blink(landmarks: np.ndarray)`：眨眼检测
- `detect_head_pose(landmarks: np.ndarray)`：头部姿态检测
- `detect_mouth_open(landmarks: np.ndarray)`：张嘴检测
- `check_liveness(frames: List[np.ndarray], landmarks_list: List[np.ndarray]) -> bool`：综合活体检测

## app/models/ 目录

### __init__.py
**功能**：模型模块初始化。

### db.py
**功能**：数据库操作封装。

**主要函数**：
- `init_schema()`：初始化数据库表结构
- `execute(sql: str, params: tuple = ())`：执行 SQL
- `query_one(sql: str, params: tuple = ())`：查询单行
- `query_all(sql: str, params: tuple = ())`：查询多行

## app/routes/ 目录

### __init__.py
**功能**：路由模块初始化。

### api_attendance.py
**功能**：考勤 API，处理实时考勤验证和记录查询。

**主要函数**：
- `issue_challenge()`：发起活体挑战
- `verify_and_recognize()`：验证并识别
- `get_records()`：获取考勤记录
- `export_records()`：导出记录为 Excel

### api_group.py
**功能**：合照 API，处理多人合照识别和活动分析。

**主要函数**：
- `upload_group_photo()`：上传合照并识别
- `get_activities()`：获取活动列表
- `analyze_activity()`：分析活动情绪

### api_stats.py
**功能**：统计 API，提供考勤和情绪统计数据。

**主要函数**：
- `get_stats()`：获取统计数据

### api_students.py
**功能**：学生管理 API，处理学生录入、批量导入、账号管理。

**主要函数**：
- `add_student()`：添加单个学生
- `batch_import()`：批量导入学生
- `list_students()`：列出学生
- `create_account()`：创建学生账号
- `parse_student_filename()`：解析文件名
- `add_or_update_student_from_image()`：从图像添加/更新学生

### auth_routes.py
**功能**：认证路由，处理登录、登出、用户创建。

**主要函数**：
- `login_page()`：登录页面
- `api_login()`：API 登录
- `api_logout()`：API 登出
- `api_me()`：获取当前用户
- `api_create_user()`：教师创建用户

### pages.py
**功能**：页面路由，提供前端页面。

**主要函数**：
- `dashboard()`：仪表板页面
- `students()`：学生管理页面
- `attendance()`：考勤页面
- `group_photo()`：合照页面
- `records()`：记录页面
- `stats()`：统计页面

## tests/ 目录

### test_attendance_frontend.js
**功能**：前端考勤测试脚本。

### test_attendance_verify.py
**功能**：后端考勤验证测试。

### test_face_engine.py
**功能**：人脸引擎测试。

### test_liveness_model.py
**功能**：活体检测模型测试。

## 数据和模型目录

### data/
**功能**：存放数据库文件（attendance.db）。

### gfpgan/
**功能**：GFPGAN 模型权重和配置。

### liveness/
**功能**：活体检测模型和权重。

### models/
**功能**：存放 dlib 模型文件和 GFPGAN 模型。

### static/ 和 templates/
**功能**：前端静态文件和 HTML 模板（不包含主要函数）。