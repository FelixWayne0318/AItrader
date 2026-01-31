#!/bin/bash
# ============================================
# AlgVex Web Frontend Setup Script
# 用于安装和配置 Web 前端服务
# ============================================

set -e

echo "========================================"
echo "   AlgVex Web Frontend 安装脚本"
echo "   $(date)"
echo "========================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检测项目路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}[ERROR] 找不到 frontend 目录: $FRONTEND_DIR${NC}"
    exit 1
fi

echo -e "${GREEN}[1/6] 项目路径: $FRONTEND_DIR${NC}"

# 检查 Node.js
echo -e "${GREEN}[2/6] 检查 Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}[ERROR] Node.js 未安装，请先安装 Node.js 18+${NC}"
    echo "运行: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"
    exit 1
fi
echo "Node.js 版本: $(node -v)"

# 安装 PM2
echo -e "${GREEN}[3/6] 安装 PM2 进程管理器...${NC}"
if ! command -v pm2 &> /dev/null; then
    sudo npm install -g pm2
    echo -e "${GREEN}PM2 安装完成${NC}"
else
    echo "PM2 已安装: $(pm2 -v)"
fi

# 安装依赖
echo -e "${GREEN}[4/6] 安装前端依赖...${NC}"
cd "$FRONTEND_DIR"
npm install

# 构建前端
echo -e "${GREEN}[5/6] 构建前端...${NC}"
npm run build

# 配置 PM2
echo -e "${GREEN}[6/6] 配置 PM2 服务...${NC}"

# 停止已有的服务
pm2 delete algvex-frontend 2>/dev/null || true

# 启动服务
pm2 start npm --name "algvex-frontend" -- start

# 配置开机自启
echo -e "${YELLOW}配置开机自启动...${NC}"
pm2 startup systemd -u $USER --hp $HOME 2>/dev/null || true
pm2 save

echo ""
echo "========================================"
echo -e "${GREEN}   安装完成！${NC}"
echo "========================================"
echo ""
echo "PM2 状态:"
pm2 status
echo ""
echo "常用命令:"
echo "  pm2 status          # 查看状态"
echo "  pm2 logs            # 查看日志"
echo "  pm2 restart all     # 重启服务"
echo "  pm2 monit           # 实时监控"
echo ""
echo "前端运行在: http://localhost:3000"
echo ""
