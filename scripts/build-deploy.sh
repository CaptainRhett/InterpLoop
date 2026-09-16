#!/usr/bin/env bash

set -euo pipefail

# =========================
# 配置
# =========================
PROJECT_DIR="/home/ubuntu/tz"
BACKEND_REQUIREMENTS="$PROJECT_DIR/backend/requirements.txt"
FRONTEND_DIR="$PROJECT_DIR/frontend"
BUILD_DIR="$FRONTEND_DIR/dist"

CONDA_ENV="tz"
BACKEND_SERVICE="tz-backend.service"

DEPLOY_DIR="/var/www/app1"


# =========================
# 日志函数
# =========================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}


# =========================
# 检查环境
# =========================
log "Checking environment..."

if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda not found"
    exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
    echo "ERROR: frontend directory not found: $FRONTEND_DIR"
    exit 1
fi

if [ ! -f "$BACKEND_REQUIREMENTS" ]; then
    echo "ERROR: backend requirements not found: $BACKEND_REQUIREMENTS"
    exit 1
fi

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
    echo "ERROR: package.json not found"
    exit 1
fi


# =========================
# 安装后端依赖
# =========================
cd "$PROJECT_DIR"

log "Installing backend dependencies..."

conda run -n "$CONDA_ENV" python -m pip install -r "$BACKEND_REQUIREMENTS"


# =========================
# 检查后端
# =========================
log "Checking backend application..."

conda run --no-capture-output -n "$CONDA_ENV" python -c 'from backend.wsgi import app; print("Backend loaded successfully")'


# =========================
# 进入前端目录
# =========================
cd "$FRONTEND_DIR"


# =========================
# 安装依赖
# =========================
if [ -f "package-lock.json" ]; then
    log "Installing dependencies with npm ci..."
    conda run -n "$CONDA_ENV" npm ci
else
    log "package-lock.json not found, using npm install..."
    conda run -n "$CONDA_ENV" npm install
fi


# =========================
# 构建前端
# =========================
log "Building frontend..."

conda run -n "$CONDA_ENV" npm run build


# =========================
# 检查构建结果
# =========================
if [ ! -d "$BUILD_DIR" ]; then
    echo "ERROR: build directory not found: $BUILD_DIR"
    exit 1
fi

if [ ! -f "$BUILD_DIR/index.html" ]; then
    echo "ERROR: index.html not found in $BUILD_DIR"
    exit 1
fi


# =========================
# 部署
# =========================
log "Deploying to $DEPLOY_DIR..."

sudo mkdir -p "$DEPLOY_DIR"

# 清除旧文件
sudo find "$DEPLOY_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

# 复制新的构建结果
sudo cp -a "$BUILD_DIR"/. "$DEPLOY_DIR"/

# 保证 nginx 可以读取
sudo chmod -R a+rX "$DEPLOY_DIR"


# =========================
# 检查 Nginx
# =========================
log "Checking nginx configuration..."

sudo nginx -t


# =========================
# Reload Nginx
# =========================
log "Reloading nginx..."

sudo systemctl reload nginx


# =========================
# Restart Backend
# =========================
log "Restarting backend service..."

sudo systemctl restart "$BACKEND_SERVICE"

log "Checking backend service status..."

sudo systemctl is-active --quiet "$BACKEND_SERVICE"


# =========================
# 完成
# =========================
log "Application deployed successfully."

echo
echo "Deployment directory:"
echo "  $DEPLOY_DIR"
echo
echo "Backend service:"
echo "  $BACKEND_SERVICE"
echo
echo "Access:"
echo "  https://82.156.212.123/"
