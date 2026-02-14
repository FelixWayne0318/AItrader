#!/bin/bash
#
# AlgVex Web 一键部署脚本
# 用途：部署前端和后端，解决所有已知问题
#
# 使用方法：
#   chmod +x web/deploy_all.sh
#   ./web/deploy_all.sh
#

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_step() {
    echo -e "${BLUE}==== $1 ====${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 错误处理
handle_error() {
    print_error "部署失败: $1"
    echo ""
    echo "请查看上方错误信息，或运行以下命令获取日志："
    echo "  pm2 logs algvex-backend --lines 100"
    echo "  pm2 logs algvex-frontend --lines 100"
    exit 1
}

# 检查是否在正确的目录
if [ ! -f "CLAUDE.md" ] || [ ! -d "web" ]; then
    handle_error "请在项目根目录运行此脚本 (/home/linuxuser/nautilus_AItrader)"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          AlgVex Web 一键部署脚本 v1.0                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# 步骤 1: 拉取最新代码
# ============================================================
print_step "步骤 1/7: 拉取最新代码"

git pull origin claude/trading-evaluation-standards-qBQP8 || handle_error "Git 拉取失败"

print_success "代码拉取完成"
echo "当前 commit:"
git log --oneline -1
echo ""

# ============================================================
# 步骤 2: 检查后端虚拟环境
# ============================================================
print_step "步骤 2/7: 检查后端虚拟环境"

BACKEND_DIR="web/backend"
VENV_DIR="$BACKEND_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    print_warning "后端虚拟环境不存在，正在创建..."
    cd $BACKEND_DIR
    python3 -m venv venv || handle_error "创建虚拟环境失败"
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt || handle_error "安装后端依赖失败"
    deactivate
    cd ../..
    print_success "虚拟环境创建完成"
else
    print_success "后端虚拟环境已存在"

    # 检查是否需要更新依赖
    print_warning "检查后端依赖更新..."
    cd $BACKEND_DIR
    source venv/bin/activate
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt --upgrade > /dev/null 2>&1 || print_warning "依赖更新失败，使用现有版本"
    deactivate
    cd ../..
    print_success "后端依赖检查完成"
fi
echo ""

# ============================================================
# 步骤 3: 检查前端依赖
# ============================================================
print_step "步骤 3/7: 检查前端依赖"

FRONTEND_DIR="web/frontend"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    print_warning "前端依赖未安装，正在安装..."
    cd $FRONTEND_DIR
    npm install || handle_error "安装前端依赖失败"
    cd ../..
    print_success "前端依赖安装完成"
else
    print_success "前端依赖已存在"
fi
echo ""

# ============================================================
# 步骤 4: 清除前端缓存并重建
# ============================================================
print_step "步骤 4/7: 清除前端缓存并重建"

cd $FRONTEND_DIR

# 清除 .next 缓存
if [ -d ".next" ]; then
    print_warning "清除 .next 缓存..."
    rm -rf .next
    print_success ".next 缓存已清除"
else
    print_success ".next 缓存不存在，跳过"
fi

# 重新构建
print_warning "重新构建前端 (这可能需要 1-2 分钟)..."
npm run build || handle_error "前端构建失败"
print_success "前端构建完成"

cd ../..
echo ""

# ============================================================
# 步骤 5: 停止旧服务 (如果存在)
# ============================================================
print_step "步骤 5/7: 停止旧服务"

# 检查 PM2 是否已安装
if ! command -v pm2 &> /dev/null; then
    handle_error "PM2 未安装，请先安装: npm install -g pm2"
fi

# 停止所有 algvex 相关服务 (忽略错误)
pm2 stop algvex-backend algvex-frontend 2>/dev/null || print_warning "没有运行中的服务需要停止"
pm2 delete algvex-backend algvex-frontend 2>/dev/null || print_warning "没有已注册的服务需要删除"

print_success "旧服务已清理"
echo ""

# ============================================================
# 步骤 6: 从 ecosystem 配置启动服务
# ============================================================
print_step "步骤 6/7: 启动前后端服务"

cd web

# 启动服务
pm2 start ecosystem.config.js || handle_error "启动服务失败"

# 保存 PM2 配置
pm2 save || print_warning "PM2 配置保存失败 (非致命错误)"

cd ..
print_success "服务启动完成"
echo ""

# ============================================================
# 步骤 7: 等待服务启动并验证
# ============================================================
print_step "步骤 7/7: 验证服务状态"

print_warning "等待服务启动 (5 秒)..."
sleep 5

# 显示 PM2 状态
echo ""
pm2 status
echo ""

# 检查后端健康
print_warning "检查后端健康状态..."
HEALTH_CHECK=$(curl -s http://localhost:8000/health 2>/dev/null || echo "FAILED")

if [[ $HEALTH_CHECK == *"healthy"* ]]; then
    print_success "后端健康检查通过: $HEALTH_CHECK"
else
    print_error "后端健康检查失败"
    echo "后端最近日志:"
    pm2 logs algvex-backend --lines 20 --nostream
    handle_error "后端启动失败"
fi

# 检查前端
print_warning "检查前端状态..."
FRONTEND_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")

if [ "$FRONTEND_CHECK" = "200" ]; then
    print_success "前端健康检查通过 (HTTP $FRONTEND_CHECK)"
else
    print_error "前端健康检查失败 (HTTP $FRONTEND_CHECK)"
    echo "前端最近日志:"
    pm2 logs algvex-frontend --lines 20 --nostream
    handle_error "前端启动失败"
fi

echo ""

# ============================================================
# 部署成功
# ============================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                  ✓ 部署成功完成！                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
print_success "前端: http://139.180.157.152:3000"
print_success "后端: http://139.180.157.152:8000"
print_success "健康检查: http://139.180.157.152:8000/health"
echo ""
echo "验证清单:"
echo "  1. 访问首页: http://139.180.157.152:3000"
echo "     - ✓ 性能统计卡片"
echo "     - ✓ 交易质量评分卡片 (新功能)"
echo ""
echo "  2. 访问性能页: http://139.180.157.152:3000/performance"
echo "     - ✓ 性能统计"
echo "     - ✓ 交易评估表格 (新功能)"
echo ""
echo "  3. 访问图表页: http://139.180.157.152:3000/chart"
echo "     - ✓ TradingView 图表"
echo "     - ✓ AI 分析侧边栏"
echo "     - ✓ 交易质量面板 (新功能)"
echo ""
echo "  4. 访问管理后台: http://139.180.157.152:3000/admin/dashboard"
echo "     - ✓ 系统信息"
echo "     - ✓ Trade Quality 标签页 (新功能)"
echo ""
echo "如果遇到问题，运行以下命令查看日志："
echo "  pm2 logs algvex-backend --lines 100"
echo "  pm2 logs algvex-frontend --lines 100"
echo ""
