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

教师登录码由 `TEACHER_CODE` 控制。

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

前端构建：

```bash
./scripts/build-frontend.sh
```

构建结果在 `frontend/dist/`，可由 Nginx 托管，并将 `/api` 反向代理到 Flask。

## 功能范围

- 学生登录：学号 + 姓名。
- 教师登录：教师码。
- 闭环练习：输入语料、设置评价参数、TTS 播放、浏览器录音、ASR、AI 评价、归档。
- NumSprint：数字专项训练。
- InterpCue：语料逐句播放。
- PromptForge：口译评价提示词生成。
- FeedbackLog：反馈文本拆分、保存、CSV 导出。
- 学习统计：练习次数、完成数、平均评价、最近记录。
