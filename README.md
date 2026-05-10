# 班级考勤系统（融合人脸识别 / 活体检测 / 情绪分析）

> 内容安全实验课程设计 —— BS 架构 · Flask + dlib + DeepFace + Chart.js

## 一、功能一览

| 模块 | 关键能力 |
| --- | --- |
| 基础考勤 | 浏览器实时摄像头采集 → 动作活体检测（眨眼/张嘴/转头）→ 人脸 1:N 匹配 → 写入考勤记录，支持按日期/学号筛选 + Excel 导出 |
| 合照识别 | 上传大合照（10–50 人），后端批量人脸检测 → 匹配学生 → 自动生成参与名单与活动频次统计（柱状图/表格） |
| 情绪分析 | 考勤、合照流程同步调用 DeepFace 做情绪识别（7 类），后端落库，前端饼图 + 时间折线 |
| 安全防护 | 随机一次性活体挑战（1~2 个动作），抗静态照片/重放视频；教师/学生角色权限隔离；上传大小限制 32 MB；模型懒加载 |

## 二、项目结构

```
final/
├── run.py                        启动入口
├── manage.py                     CLI 工具：initdb / adduser
├── config.py                     全局配置（阈值、路径、密钥）
├── requirements.txt
├── shape_predictor_68_face_landmarks.dat   (需下载)
├── dlib_face_recognition_resnet_model_v1.dat (需下载)
├── data/                         SQLite 数据库
├── app/
│   ├── __init__.py               Flask 工厂
│   ├── face_engine.py            dlib 检测/编码/匹配 + DeepFace 情绪
│   ├── liveness.py               EAR/MAR/yaw + 动作状态机 + 会话管理
│   ├── auth.py                   登录/权限装饰器
│   ├── models/                   SQLite 数据访问层
│   ├── routes/                   pages + auth + students/attendance/group/stats API
│   ├── templates/                Jinja 模板
│   └── static/
│       ├── css/style.css
│       ├── js/                   common / attendance / students / group / records / stats
│       └── uploads/              学生人脸照 + 合照
└── 5-1.py / 5-2.py / 5-3.py      参考代码（保留）
```

## 三、运行环境

- Python 3.9 ~ 3.11（dlib 在更高版本编译可能需自行处理）
- Windows / macOS / Linux 均可
- 浏览器：Chrome / Edge ≥ 100（getUserMedia 需要 https 或 localhost）

## 四、部署步骤

### 1. 安装依赖

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

> dlib 编译失败时可改装 `dlib-binary`，或下载对应平台的 wheel。

### 2. 下载模型文件

把以下两个文件放到项目根目录（与 `run.py` 同级）：

- [`shape_predictor_68_face_landmarks.dat`](http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2)
- [`dlib_face_recognition_resnet_model_v1.dat`](http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2)

下载后用 `bzip2 -d` 解压。

DeepFace 首次运行会自动下载情绪识别模型至 `~/.deepface/`，需联网。

### 3. 初始化与启动

```bash
python manage.py initdb
python run.py
```

浏览器打开 <http://localhost:5000> ，默认教师账号：

```
用户名：admin
密码：admin123
```

### 4. 录入学生人脸库

- 教师登录 → 「学生管理」
  - 单条添加：填写学号/姓名/班级 + 上传一张正面免冠照
  - 批量导入：选中多张图片，文件名格式 `学号_姓名_班级.jpg`（班级可省）

### 5. 创建学生账号（可选）

```bash
python manage.py adduser 2024001 123456 student <student_id>
```

`<student_id>` 是 students 表自增 ID（在「学生管理」页可见）。学生登录后只能查看自己的考勤与情绪记录。

## 五、活体检测说明（核心防伪造）

**思路**：服务端在每次考勤会话生成 2 个随机动作（眨眼 / 张嘴 / 左转 / 右转），前端连续采集 ~25 帧（5 秒），整体提交。后端在帧序列上跑状态机：

| 动作 | 判定 |
| --- | --- |
| 眨眼 | 双眼平均 EAR 出现 `< 0.21` 后又回到 `> 0.27` |
| 张嘴 | 内唇 MAR 峰值 `> 0.55` 且与基线差 > 0.15 |
| 左 / 右转头 | solvePnP 计算 yaw，绝对值超过 18° |

由于挑战是**随机+一次性 token**，单张照片永远无法完成动作；预录视频也会因挑战不固定而失败。

阈值在 `config.py` 调整。

## 六、API 速查

| 方法 + 路径 | 说明 | 权限 |
| --- | --- | --- |
| `POST /api/login` `/api/logout` `/api/me` | 登录/注销/会话信息 | 公开 |
| `GET/POST/PUT/DELETE /api/students` | 学生 CRUD（教师） | teacher |
| `POST /api/students/import` | 批量导入 | teacher |
| `POST /api/attendance/challenge` | 申请活体挑战 token | login |
| `POST /api/attendance/verify` | 提交帧序列校验 + 比对 | login |
| `GET /api/attendance/records` | 考勤记录（带筛选） | login |
| `GET /api/attendance/export` | 导出 Excel | teacher |
| `POST /api/group/upload` | 上传合照并识别 | teacher |
| `GET /api/group/activities` | 活动列表 | teacher |
| `GET /api/stats/overview` | 仪表盘汇总 | login |
| `GET /api/stats/activities` | 活动参与频次 | login |
| `GET /api/stats/emotions` `/timeline` | 情绪分布 / 趋势 | login |

## 七、数据库表

- `users` —— 账号（teacher / student）
- `students` —— 学生信息 + 128-d 特征 BLOB
- `attendance_records` —— 考勤流水
- `activities` `activity_participation` —— 活动 + 学生参与
- `emotions` —— 情绪记录（关联学号、时间、来源）

详见 [app/models/db.py](app/models/db.py)。

## 八、常见问题

1. **摄像头无法开启**：浏览器要求 `https://` 或 `localhost`。本地运行已支持 `localhost`；局域网部署可使用 `mkcert` 起 https，或在 Chrome `chrome://flags` 临时把 IP 加入安全 origins。
2. **「未检测到人脸」**：确保正面、光线良好；学生照尽量为单人证件照风格。
3. **DeepFace 首次较慢**：会下载模型；离线环境可手动下载到 `~/.deepface/weights/`。
4. **dlib 安装失败**：建议 `pip install dlib-binary` 或安装 Visual C++ Build Tools。

## 九、安全注意事项

- 学生照片本地存储于 `app/static/uploads/students/`，**禁止泄露至公网**；学生人脸特征以 BLOB 形式与照片分离存储，可单独擦除。
- 默认密钥 `SECRET_KEY` 仅供演示，生产部署务必改为强随机值并使用 https。
- 上传文件大小限制 32MB（`config.MAX_CONTENT_LENGTH`），防止 DOS。
