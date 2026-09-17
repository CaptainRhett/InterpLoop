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
录音及名单文件上传、CSV / Excel 导出。部署时沿用 `/api` 的反向代理即可访问文档。

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

先保存，再点击“测试模型接口”，或选择语种后现场录音；停止录音后会自动测试识别接口。测试始终调用真实的已保存服务，
显示响应/识别文字、成功状态和耗时，可能产生服务商用量费用。测试模型的连通性不等于保证该模型
能够稳定输出口译评价结构，实际评价仍会执行结构校验。现场识别录音会在浏览器中转换为
16kHz、16bit、单声道 PCM，最长 30 秒。临时测试文件会在调用结束后删除。
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

AI 对话左侧提供会话列表、新建和历史切换。正式账号的会话及消息保存到数据库，刷新页面、重新登录或重启后端后仍可读取。
列表按创建顺序分页，消息按会话内固定轮次分页，避免依赖时间戳排序造成顺序不确定。
所有对话接口均要求有效的正式账号或游客会话，且只允许会话所属用户访问；管理员也不能通过这些接口读取其他人的聊天。
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

## 游客试用

登录页的“游客试用，无需登录”可直接进入全部学习功能：闭环练习、数字专项、语料播放、提示词设置、
反馈记录、学习统计和 AI 学习助手。游客无需加入班级，不能访问账号管理、系统配置、教学关系或其他人的数据。
正式账号的记录列表、统计和导出不包含游客试用数据。

`POST /api/auth/guest` 创建独立的临时身份，通过 HttpOnly 会话 Cookie 保存随机 token；数据库只保存 token 的 SHA-256 摘要。
每次续期后有效 **2 小时**，可通过 `GUEST_SESSION_SECONDS=7200` 配置。页面根据点击、输入或重新聚焦等操作自动续期
（最多每分钟一次），顶部也可点击“继续试用 / 续期”。续期保留身份、当前对话、练习及录音，并同步其他标签页的有效期。
仅打开页面但长期不操作不会持续续期；重复进入入口不会创建新身份。游客不会创建可登录的正式账号。
`POST /api/auth/guest/renew` 仅续期当前仍有效的游客会话，新的到期时间从当前时间计算，不按点击次数叠加。

未继续使用或续期而到期时，接口拒绝访问，页面清空当前试用状态并回到登录页；已清理的会话无法恢复，重新试用会创建新会话。
退出试用或成功切换到正式账号时，立即删除游客身份、聊天、
练习、评价版本、归档、反馈、相关审计记录及录音文件；失败上传和重录留下的旧音频也会清理。
游客记录在有效期内临时存入数据库，录音单独存入 `UPLOAD_DIR/guests/<token摘要>/`。
后端启动和请求时会清理已过期数据，后台线程每秒检查一次，即使浏览器关闭、没有后续请求也会清理。
服务停机期间无法执行物理删除，重新启动时会补清理。过期后才完成的 AI 回复或识别结果不会保留。
清理为数据库记录和文件的逻辑删除；已生成的外部数据库备份遵循备份系统自己的保留策略。

部署时必须同时更新前后端。后端启动时自动创建 `guest_sessions` 表，不需要手动修改正式账号的数据：

```bash
conda run -n tz python -m pip install -r backend/requirements.txt
# 先验证新代码能启动，成功后再重启生产服务
conda run --no-capture-output -n tz python -c 'from backend.wsgi import app; print("后端加载成功")' &&
sudo systemctl restart tz-backend.service
./scripts/build-deploy.sh
```

可手动补做清理：`conda run -n tz flask --app backend.wsgi:app cleanup-guests`。

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

## 学习记录导出

学生可在练习详情页选择 CSV 或 Excel（`.xlsx`），点击“导出本次记录”，下载已保存的当前结果、
全部历史评价和正式归档快照。尚未提交的 ASR 编辑不包含在导出中。
统计页支持批量导出练习和评价历史，反馈记录页支持导出反馈；所有入口均可选择两种格式。
学生仅导出自己的数据，教师仅导出授课范围内的数据，管理员按现有管理范围导出；游客不可导出。

接口保留原有 `.csv` 地址，同时提供对应 `.xlsx` 地址：
`/api/practices/{id}/export.csv`、`/api/practices/export.csv`、
`/api/practices/evaluation-versions/export.csv`、`/api/feedback-logs/export.csv`。
CSV 使用 UTF-8 BOM；Excel 保留学号等文本字段并提供表头筛选和冻结。

## 功能范围

- 学生登录：管理员导入学号账号和初始密码，首次登录强制改密。
- 正式账号：密码哈希、首次改密、管理员重置、账号禁用与登录审计。
- 教学权限：学期、班级、课程、学生选课和教师授课范围的后端数据隔离。
- 闭环练习：支持中日、中英双向口译，包含语料输入、参数设置、TTS 播放、浏览器录音、ASR、AI 评价和显式归档。
- NumSprint：数字专项训练。
- InterpCue：语料逐句播放。
- PromptForge：口译评价提示词生成。
- FeedbackLog：反馈文本拆分、保存、LoopPractice 自动同步和 CSV / Excel 导出。
- 练习档案：学生与教师可回看完整结果、修改 ASR 后重新评价、查看历史版本并重新归档。
- 学习统计：练习次数、正式归档数、平均评价、档案列表和 CSV / Excel 导出。

admin9527
Zhouxingxing9527
