# InterpLoop

自主口译实训与反馈平台。项目由 `ref/` 下的静态原型整理为 Vue3 前端、Tailwind 样式、Flask 后端和 SQLite 数据存储。

## 环境

本项目按 conda 环境 `tz` 运行：

```bash
conda activate tz
```

如果不手动激活环境，也可以使用仓库里的脚本；脚本内部会使用 `conda run -n tz ...`。

## 配置

```bash
cp .env.example .env
```

默认 `USE_MOCK_SERVICES=true`，没有豆包和讯飞密钥也能跑通闭环演示。接入真实服务时填写：

- `DOUBAO_API_KEY`
- `DOUBAO_MODEL`
- `XUNFEI_APP_ID`
- `XUNFEI_API_KEY`
- `XUNFEI_API_SECRET`

系统支持日→中、中→日、英→中、中→英四个练习方向。使用真实讯飞语音服务时，可通过
`XUNFEI_TTS_VOICE_ZH`、`XUNFEI_TTS_VOICE_JA` 和 `XUNFEI_TTS_VOICE_EN` 配置各语种在讯飞
控制台中已授权的发音人；英文发音人留空时会自动使用浏览器英文语音。

学生、教师和管理员统一使用“账号 + 密码”登录。后端校验 `UserAccount` 后从关联的 `User.role`
读取身份，不提供学号姓名免密入口或共享教师码入口。

首次部署先创建管理员：

```bash
conda run -n tz flask --app backend.wsgi:app create-admin
```

管理员登录后可在“账号与权限”页面导入 XLSX/CSV 学生名单、创建教师账号、重置或禁用账号，
并绑定教师负责的班级与课程。名单模板见 `docs/student-import-template.csv`。初始密码只在创建或
导入结果中返回一次，数据库只保存 Werkzeug 密码哈希；学生首次登录必须修改初始密码。

后端权限范围固定为：

- 学生只能读取和修改自己的练习及反馈。
- 教师只能访问授课关系中对应班级、课程的数据，包括详情、统计和导出。
- 管理员可管理账号、学期、班级、课程、选课、授课范围并查看审计记录。

生产 HTTPS 环境应设置 `SESSION_COOKIE_SECURE=true`，并使用随机高强度 `SECRET_KEY`。

## 开发启动

后端：

```bash
./scripts/dev-backend.sh
```

前端：

```bash
./scripts/dev-frontend.sh
```

访问：

```text
http://localhost:5173
```

## Swagger / OpenAPI

安装后端依赖并启动后，可访问：

- Swagger UI：<http://localhost:5000/api/docs>
- OpenAPI 3.0.3 JSON：<http://localhost:5000/api/openapi.json>

文档涵盖登录、练习、语音、反馈、提示词、统计、管理后台和 AI 对话接口，支持 JSON 请求、
录音及名单文件上传、CSV 导出。部署时沿用 `/api` 的反向代理即可访问文档。

在 Swagger UI 中展开 `POST /api/auth/login`，点击 **Try it out**，填写账号密码并执行。
浏览器会保存并自动携带 Session Cookie；首次登录须先执行 `POST /api/auth/change-password`。
随后可按账号权限调试其他接口，无需手动填写 Authorize。调试操作会实际修改数据，请使用测试账号。

Swagger UI 的 JS/CSS 从 jsDelivr 加载，浏览器需能访问该 CDN。配置集中在
`backend/app/config.py`，可通过自定义 Flask 配置类覆盖 `OPENAPI_SWAGGER_UI_URL` 指向自托管资源。
文档定义位于 `backend/app/openapi.py`；新增或修改接口时同步更新 `OPERATIONS`，
路径与路径参数从 Flask 路由表生成。文档不会额外改变接口参数校验行为。
集成配置参考 [flask-smorest 官方文档](https://flask-smorest.readthedocs.io/en/latest/openapi.html)。

运行后端测试（包含文档入口、路由覆盖和 Cookie 登录验证）：

```bash
conda run -n tz python -m unittest discover -s backend/tests -v
```

## 单机部署建议

后端生产运行：

```bash
conda run -n tz python -m pip install -r backend/requirements.txt
conda run -n tz gunicorn -w 4 -b 0.0.0.0:5000 backend.wsgi:app
```

SQLite 已在后端启用 WAL、`busy_timeout` 和外键约束，适合 50 人左右的课堂并发。录音文件保存在 `var/uploads/`，数据库保存在 `instance/interploop.sqlite3`。
升级后首次启动会自动执行幂等的数据库兼容升级、创建评价版本和归档快照表，并将已有 AI 评价登记为第 1 版；原练习与反馈数据不会被覆盖。

前端构建：

```bash
./scripts/build-frontend.sh
```

构建结果在 `frontend/dist/`，可由 Nginx 托管，并将 `/api` 反向代理到 Flask。

## 管理员系统配置

管理员在“账号与权限”页面顶部的“系统配置 · 第三方服务”中配置：

- 模型服务类型（豆包 / 兼容 OpenAI Chat Completions）、API 基础地址、模型 ID、API Key、超时。
- 语音识别类型（讯飞 / 兼容 OpenAI 音频转写）；讯飞配置 App ID、API Key、API Secret、主机和识别领域，兼容服务配置基础地址、模型 ID 和 API Key。
- 业务是否使用模拟服务。关闭后使用真实服务；模型缺少凭据时会报错，不再静默返回模拟结果。

先保存，再点击“测试模型接口”或上传录音点击“测试识别接口”。测试始终调用真实的已保存服务，
显示响应/识别文字、成功状态和耗时，可能产生服务商用量费用。测试模型的连通性不等于保证该模型
能够稳定输出口译评价结构，实际评价仍会执行结构校验。识别测试文件不超过 1 MB；讯飞要求
16kHz、16bit、单声道 PCM/WAV，且不超过 30 秒。临时测试文件会在调用结束后删除。
兼容识别接口使用 `/audio/transcriptions`，提交 `file`、`model` 和 `language`，参见
[音频转写接口参考](https://platform.openai.com/docs/api-reference/audio/createTranscription)。

Web 配置存入数据库，优先级为 **Web 覆盖 > 进程环境变量 / `.env` > 默认值**。
Web 仅保存修改过的字段，未覆盖字段沿用环境配置；页面显示 Web 覆盖字段，点击“全部恢复环境配置”
可删除 Web 覆盖。API 更新时传入 `null` 可单独恢复一个字段。Web 保存后后续请求立即生效，
修改 `.env` 则需重启后端；已有进程环境变量优先于 `.env` 的同名配置。
模型配置使用 `LLM_PROVIDER`、`DOUBAO_BASE_URL`、`DOUBAO_MODEL`、`DOUBAO_API_KEY`，
其中 `DOUBAO_*` 同样用于兼容 OpenAI 协议的模型。识别使用 `ASR_PROVIDER`，兼容协议使用
`ASR_BASE_URL`、`ASR_MODEL`、`ASR_API_KEY`；讯飞使用 `XUNFEI_*`，识别领域为 `XUNFEI_IAT_DOMAIN`。
完整变量见 `.env.example`。API 密钥使用 Fernet 加密，
页面不回显，留空保留原值；审计日志仅记录改动字段和测试状态。
加密密钥由应用 `SECRET_KEY` 派生：应使用稳定的高强度值，备份/迁移时保留该值，
不要直接轮换它，否则现有加密配置无法解密。首次使用此功能需安装更新后的后端依赖并重启后端，
启动时自动创建配置表。对应接口和上传格式已加入 Swagger。

## 智能体对话历史

AI 对话左侧提供会话列表、新建和历史切换。会话及消息保存到数据库，刷新页面、重新登录或重启后端后仍可读取。
列表按创建顺序分页，消息按会话内固定轮次分页，避免依赖时间戳排序造成顺序不确定。
所有对话接口均要求登录，且只允许会话所属用户访问；管理员也不能通过这些接口读取其他人的聊天。
旧版本仅保存在浏览器内存中的对话无法追溯恢复。

会话使用 UUIDv4 公共 ID 和数据库自增主键，UUID 有唯一约束，碰撞时重新生成，绝不复用已有会话。
每条发送请求使用独立 UUID，数据库约束 `(conversation_id, request_id)` 和 `(conversation_id, sequence)` 唯一。
SHA-256 仅用于保存内容摘要，不用作会话身份或去重依据；请求重试还校验完整原文，即使摘要碰撞也不会合并内容。
同一会话通过版本号和数据库条件更新控制并发，生成期间不占用写事务；过期尝试的迟到回复不能覆盖后续结果。
生成失败时保留用户消息并允许重试同一轮。服务端仅从本人会话中组装最近完整轮次作为模型上下文，不信任客户端历史。
页面切换会话、账号或离开页面时会丢弃过期请求结果，防止旧回复写到当前对话框。

升级后重启后端自动创建 `chat_conversations`、`chat_turns` 表，无需修改既有练习数据。
`POST /api/llm/chat` 改为提交 `conversation_id`、`request_id`、`expected_version`、`message`；
会话创建、列表和历史接口见 Swagger，旧的无登录 `messages` 数组调用方式已取消。

## 逐句闭环练习

输入原文后自动识别中文、日文和英文句界，按“播放本句 → 录制口译 → 识别并校对 → 确认下一句”
完成练习。原文播放支持暂停/继续；录音前可选择“开始录音时隐藏原文”，默认开启。
每句录音和识别结果分别保存，重录只替换对应句子，全部完成后汇总文字与完整原文一起评价。

新评价统一使用 1–10 分制及固定的总评、优点、问题、改进建议、参考译文结构。
后端校验 AI 返回的字段和分数，不合格时提示重新生成，避免写入错误评价版本。
确认归档后，结构化内容直接同步到反馈记录；复制评价文本导入时也可按固定标题拆分。
历史评价保留原分数；统计页将旧字母等级按原五分制映射乘以 2，与新十分制分数一起计算平均分。
Mock 模式的评价用于流程演示，不代表实际口译水平。

前端自动化验证：在 `frontend` 下运行 `npm test`。测试使用模拟语音、麦克风和网络响应；
真实设备的语音播放、录音权限和上游 AI/ASR 效果需在浏览器中验证。

## 功能范围

- 学生登录：管理员导入学号账号和初始密码，首次登录强制改密。
- 正式账号：密码哈希、首次改密、管理员重置、账号禁用与登录审计。
- 教学权限：学期、班级、课程、学生选课和教师授课范围的后端数据隔离。
- 闭环练习：支持中日、中英双向口译，包含语料输入、参数设置、TTS 播放、浏览器录音、ASR、AI 评价和显式归档。
- NumSprint：数字专项训练。
- InterpCue：语料逐句播放。
- PromptForge：口译评价提示词生成。
- FeedbackLog：反馈文本拆分、保存、LoopPractice 自动同步和 CSV 导出。
- 练习档案：学生与教师可回看完整结果、修改 ASR 后重新评价、查看历史版本并重新归档。
- 学习统计：练习次数、正式归档数、平均评价、档案列表和完整 CSV 导出。

admin9527
Zhouxingxing9527
