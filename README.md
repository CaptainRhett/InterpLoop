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