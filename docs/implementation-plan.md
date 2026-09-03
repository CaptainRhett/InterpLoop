# InterpLoop Web 应用实施计划

## 1. 项目目标

将 `ref/` 下的静态原型改造成一个完整 Web 应用，技术栈为：

- 前端：Vue 3 + Vite + Tailwind CSS
- 后端：Python Flask + SQLAlchemy
- 数据库：SQLite
- 部署：单机服务器，目标支持约 50 人同时在线课堂使用

第一版包含登录、闭环练习、数字专项训练、语料播放、提示词设置、反馈归档、学习统计。`VoiceTrace` 不做独立入口，只作为闭环练习里的“录音 + ASR”模块。

## 2. 功能范围

### 2.1 登录与权限

- 学生使用“学号 + 姓名”免密码登录。
- 教师使用教师码进入管理视图。
- 学生只能查看自己的练习记录。
- 教师可以查看、筛选、导出全班记录。

### 2.2 左侧导航

应用采用后台式布局：

- 闭环练习
- 数字专项训练
- 语料播放
- 提示词设置
- 反馈记录
- 学习数据统计

### 2.3 闭环练习

闭环练习是主流程，按 5 步实现：

1. 输入中文、日文或英文语料，选择日→中、中→日、英→中或中→英方向。
2. 设置播放间隔、评审员角色、模型、严格度、评价维度。
3. 系统播放源语，学生口译，浏览器录音。
4. 上传音频，后端调用 ASR，再调用大模型生成评价。
5. 三栏展示“源语原文 | ASR识别文本 | AI评价”，确认后归档。

### 2.4 独立工具

- 数字专项训练：支持数字/词条闪现、难度、模式、间隔设置。
- 语料播放：支持文本分句、逐句播放、整段播放、TTS 声音参数。
- 提示词设置：支持预设、维度选择、严格度、提示词预览。
- 反馈记录：支持原文拆分为优点、问题、建议、总评，并导出 CSV。

## 3. 后端设计

### 3.1 目录结构

建议结构：

```text
backend/
  app/
    __init__.py
    config.py
    extensions.py
    models.py
    api/
      auth.py
      practice.py
      prompt.py
      speech.py
      stats.py
    services/
      asr.py
      llm.py
      tts.py
      export.py
      feedback_parser.py
  run.py
  requirements.txt
```

### 3.2 数据表

`users`

- `id`
- `student_no`
- `name`
- `role`
- `created_at`
- `last_login_at`

`user_accounts`

- `user_id`
- `login_id`
- `password_hash`
- `is_active`
- `must_change_password`
- `password_changed_at`

`academic_terms` / `class_groups` / `courses`

- 管理学期、班级和课程主数据

`course_enrollments`

- 绑定学生、班级和课程

`teaching_assignments`

- 绑定教师可管理的班级和课程

`practice_contexts` / `feedback_contexts`

- 固定练习及反馈产生时的学期、班级、课程权限上下文

`practice_sessions`

- `id`
- `user_id`
- `direction`
- `source_text`
- `interval_seconds`
- `model_name`
- `status`
- `created_at`
- `completed_at`

`practice_results`

- `id`
- `session_id`
- `audio_path`
- `asr_text`
- `evaluation_json`
- `score`
- `feedback_text`
- `reference_translation`
- `created_at`

`practice_evaluation_versions`

- `session_id`
- `version_number`
- `asr_text`
- `score`
- `feedback_text`
- `reference_translation`
- `evaluation_json`
- `created_by_id`
- `created_at`

`practice_archives`

- `session_id`
- `evaluation_version_id`
- `feedback_log_id`
- `source_text`
- `asr_text`
- `score`
- `feedback_text`
- `reference_translation`
- `practice_created_at`
- `evaluation_created_at`
- `archived_at`

`prompt_presets`

- `id`
- `name`
- `role_prompt`
- `task_type`
- `dimensions_json`
- `format_prompt`
- `strictness`
- `is_default`

`feedback_logs`

- `id`
- `user_id`
- `task_id`
- `feedback_type`
- `raw_text`
- `pros`
- `cons`
- `suggestions`
- `overall`
- `created_at`

### 3.3 SQLite 并发配置

为支持约 50 人同时在线，SQLite 需要：

- 启用 WAL 模式。
- 设置 `busy_timeout=5000`。
- 避免长事务。
- 音频文件存磁盘，数据库只保存路径。
- 生产环境用 `gunicorn` 多 worker 运行 Flask。

### 3.4 外部服务

第一版按真实接入设计，同时保留 mock 模式方便本地开发。

- 大模型：豆包 / 火山方舟 LLM API。
- ASR/TTS：默认接入讯飞 API。
- API 密钥只存放在后端 `.env`，前端不直接接触。

环境变量：

```text
SECRET_KEY=
DATABASE_URL=sqlite:///interploop.db
UPLOAD_DIR=instance/uploads
MOCK_EXTERNAL_SERVICES=true
DOUBAO_API_KEY=
DOUBAO_MODEL=
XUNFEI_APP_ID=
XUNFEI_API_KEY=
XUNFEI_API_SECRET=
```

## 4. API 设计

### 4.1 认证

- `POST /api/auth/login`
  - 输入：`login_id`, `password`
  - 输出：账号信息、数据库角色和可用班级课程上下文
  - 学生、教师和管理员共用该入口，权限身份从 `User.role` 读取

### 4.2 语音

- `POST /api/tts`
  - 输入：`text`, `lang`, `voice`, `speed`
  - 输出：音频文件 URL 或 base64 音频

- `POST /api/asr`
  - 输入：音频文件、语言方向、练习 ID
  - 输出：`transcript`, `confidence`, `segments`

### 4.3 闭环练习

- `POST /api/practices`
  - 创建练习记录

- `POST /api/practices/:id/evaluate`
  - 输入：ASR 文本
  - 输出：结构化评价、参考译文、评分和不可覆盖的评价版本

- `POST /api/practices/:id/archive`
  - 显式保存当前评价版本的完整快照，并同步生成 FeedbackLog 记录

- `GET /api/practices/:id`
  - 返回练习详情、当前归档快照和全部历史评价版本

- `GET /api/practices`
  - 学生查看自己的记录
  - 教师按学生、日期、方向筛选记录

- `GET /api/practices/export.csv`
  - 教师导出 CSV

- `GET /api/practices/evaluation-versions/export.csv`
  - 教师按评价版本逐行导出 CSV，用于教学分析和研究数据积累

### 4.4 统计

- `GET /api/stats/summary`
  - 返回练习次数、总时长、平均评分、趋势统计

## 5. 前端设计

### 5.1 目录结构

建议结构：

```text
frontend/
  src/
    main.js
    App.vue
    router/
    stores/
    api/
    components/
    views/
      LoginView.vue
      LoopPracticeView.vue
      NumSprintView.vue
      InterpCueView.vue
      PromptForgeView.vue
      FeedbackLogView.vue
      StatsView.vue
```

### 5.2 页面要求

- 首屏为登录页，不做营销落地页。
- 登录后进入主应用布局。
- 左侧固定导航，右侧显示当前工具。
- 控件使用 Tailwind 实现清晰、紧凑的课堂工具界面。
- 移动端可纵向排列，避免表格和三栏展示溢出。

### 5.3 关键交互

- 闭环练习中用 `MediaRecorder` 录音。
- 录音上传前显示录音时长和状态。
- ASR 或大模型失败时保留源语和录音，允许重试。
- 评价结果必须能保存、打印、导出。
- 提示词设置可以被闭环练习继承。

## 6. 测试与验收

### 6.1 后端测试

- 学生登录、教师登录。
- 练习创建、录音上传、ASR、评价、归档。
- 教师筛选和 CSV 导出。
- 外部服务失败时返回可读错误。
- 模拟 50 个并发会话创建和保存练习记录，确认无 SQLite 锁死问题。

### 6.2 前端测试

- 登录后导航正常。
- 四个独立工具可单独使用。
- 闭环 5 步流程可完整走通。
- 桌面端和移动端布局不重叠、不溢出。

### 6.3 集成验收

- 配置真实密钥后，TTS、ASR、豆包评价能完成闭环。
- 没有真实密钥时，mock 模式可以完整演示流程。
- 教师能导出学生练习记录。

## 7. 实施顺序

1. 搭建 Flask 后端骨架、数据库模型、配置管理。
2. 搭建 Vue3 + Tailwind 前端骨架和主布局。
3. 实现登录、会话、权限。
4. 迁移四个独立工具的核心逻辑。
5. 实现闭环练习 5 步流程。
6. 接入 ASR/TTS/豆包服务，并保留 mock 模式。
7. 实现反馈归档、统计、导出。
8. 做并发测试、UI 检查和部署文档。

## 8. 默认假设

- 第一版部署在一台单机服务器。
- SQLite 足够支撑 50 人课堂使用；后续多班高并发再迁移 PostgreSQL。
- 音频文件存本地磁盘，不写入 SQLite。
- 教师码通过 `.env` 配置。
- 讯飞是第一版 ASR/TTS 默认实现。
