#!/bin/bash
# ============================================================
# AItrader 一键安装脚本 v2.0
#
# 用途: 完整安装交易机器人 + 可选 Web 管理界面
# 服务器: 139.180.157.152
# 用户: linuxuser
# 仓库: https://github.com/FelixWayne0318/AItrader
#
# 组件:
#   [必装] AItrader - NautilusTrader 交易机器人
#   [可选] Algvex Web - 网站管理界面 (前端 + 后端)
#
# 使用方法:
#   方法1: 一键安装全部 (从 GitHub)
#     curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash
#
#   方法2: 仅安装交易机器人
#     curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash -s -- --trader-only
#
#   方法3: 仅安装 Web 界面
#     curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash -s -- --web-only
#
#   方法4: 本地执行
#     chmod +x reinstall.sh && ./reinstall.sh
#
# ============================================================

set -e  # 遇到错误立即退出

# ==================== 配置变量 ====================
INSTALL_DIR="/home/linuxuser/nautilus_AItrader"
WEB_DIR="/home/linuxuser/algvex"
HOME_DIR="/home/linuxuser"
ENV_PERMANENT="${HOME_DIR}/.env.aitrader"
WEB_ENV="${WEB_DIR}/backend/.env"
REPO_URL="https://github.com/FelixWayne0318/AItrader.git"
BRANCH="${AITRADER_BRANCH:-main}"
TRADER_SERVICE="nautilus-trader"
WEB_BACKEND_SERVICE="algvex-backend"
WEB_FRONTEND_SERVICE="algvex-frontend"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 安装选项 (默认全部安装)
INSTALL_TRADER=true
INSTALL_WEB=true

# ==================== 解析参数 ====================
while [[ $# -gt 0 ]]; do
    case $1 in
        --trader-only)
            INSTALL_WEB=false
            shift
            ;;
        --web-only)
            INSTALL_TRADER=false
            shift
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            exit 1
            ;;
    esac
done

# ==================== 辅助函数 ====================
print_header() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    AItrader 一键安装脚本 v2.0                  ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}安装组件:${NC}"
    if $INSTALL_TRADER; then
        echo -e "  ${GREEN}✓${NC} AItrader 交易机器人"
    else
        echo -e "  ${YELLOW}○${NC} AItrader 交易机器人 (跳过)"
    fi
    if $INSTALL_WEB; then
        echo -e "  ${GREEN}✓${NC} Algvex Web 管理界面"
    else
        echo -e "  ${YELLOW}○${NC} Algvex Web 管理界面 (跳过)"
    fi
    echo -e "${CYAN}分支:${NC} ${BRANCH}"
    echo ""
}

print_step() {
    echo ""
    echo -e "${YELLOW}[$1] $2${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# ==================== 主程序开始 ====================
print_header

STEP=1
TOTAL_STEPS=0
$INSTALL_TRADER && TOTAL_STEPS=$((TOTAL_STEPS + 5))
$INSTALL_WEB && TOTAL_STEPS=$((TOTAL_STEPS + 4))
TOTAL_STEPS=$((TOTAL_STEPS + 2))  # 基础步骤

# ==================== 1. 检查系统依赖 ====================
print_step "${STEP}/${TOTAL_STEPS}" "检查并安装系统依赖..."
STEP=$((STEP + 1))

# 检测包管理器
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    sudo apt-get update -qq
elif command -v yum &> /dev/null; then
    PKG_MANAGER="yum"
else
    print_error "不支持的系统，请使用 Ubuntu/Debian 或 CentOS"
    exit 1
fi

# 安装基础依赖
sudo $PKG_MANAGER install -y -qq curl git software-properties-common build-essential

# Python 3.11+ (AItrader 和 Web 都需要)
if ! command -v python3.11 &> /dev/null; then
    print_warning "安装 Python 3.11..."
    if [ "$PKG_MANAGER" = "apt-get" ]; then
        sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev
    fi
fi
print_success "Python 3.11 已就绪"

# 确保 python3 命令可用 (创建符号链接如果不存在)
if ! command -v python3 &> /dev/null; then
    sudo ln -sf /usr/bin/python3.11 /usr/bin/python3
fi

# Node.js 18+ (Web 需要)
if $INSTALL_WEB; then
    NODE_VERSION=$(node -v 2>/dev/null | cut -d'v' -f2 | cut -d'.' -f1 || echo "0")
    if [ "$NODE_VERSION" -lt 18 ]; then
        print_warning "安装 Node.js 18..."
        curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - 2>/dev/null
        sudo apt-get install -y -qq nodejs
    fi
    print_success "Node.js $(node -v) 已就绪"
fi

# ==================== 2. 处理配置文件 ====================
print_step "${STEP}/${TOTAL_STEPS}" "处理配置文件..."
STEP=$((STEP + 1))

# AItrader 配置
if $INSTALL_TRADER; then
    if [ -f "${ENV_PERMANENT}" ]; then
        print_success "发现 AItrader 配置: ${ENV_PERMANENT}"
    else
        if [ -f "${INSTALL_DIR}/.env" ] && [ ! -L "${INSTALL_DIR}/.env" ]; then
            cp "${INSTALL_DIR}/.env" "${ENV_PERMANENT}"
            chmod 600 "${ENV_PERMANENT}"
            print_success "已迁移配置到 ${ENV_PERMANENT}"
        else
            print_warning "AItrader 配置稍后需要手动创建"
        fi
    fi
fi

# Web 配置 (保留现有)
if $INSTALL_WEB && [ -f "${WEB_ENV}" ]; then
    WEB_ENV_BACKUP="/tmp/algvex-backend-env-backup"
    cp "${WEB_ENV}" "${WEB_ENV_BACKUP}"
    print_success "已备份 Web 配置"
fi

# ==================== AItrader 安装 ====================
if $INSTALL_TRADER; then
    # 停止服务
    print_step "${STEP}/${TOTAL_STEPS}" "停止 AItrader 服务..."
    STEP=$((STEP + 1))

    if systemctl is-active --quiet ${TRADER_SERVICE}.service 2>/dev/null; then
        sudo systemctl stop ${TRADER_SERVICE}.service
    fi
    sudo systemctl disable ${TRADER_SERVICE}.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/${TRADER_SERVICE}.service 2>/dev/null || true
    pkill -f "main_live.py" 2>/dev/null || true
    sleep 2
    print_success "AItrader 服务已停止"

    # 删除旧目录
    print_step "${STEP}/${TOTAL_STEPS}" "清理 AItrader 旧文件..."
    STEP=$((STEP + 1))

    rm -rf "${INSTALL_DIR}"
    print_success "旧文件已清理"

    # 克隆仓库
    print_step "${STEP}/${TOTAL_STEPS}" "克隆 AItrader 仓库..."
    STEP=$((STEP + 1))

    cd "${HOME_DIR}"
    git clone -b "${BRANCH}" --depth 1 "${REPO_URL}" nautilus_AItrader
    print_success "仓库已克隆"

    # 配置环境
    print_step "${STEP}/${TOTAL_STEPS}" "配置 AItrader 环境..."
    STEP=$((STEP + 1))

    cd "${INSTALL_DIR}"
    rm -f .env 2>/dev/null || true

    if [ -f "${ENV_PERMANENT}" ]; then
        ln -sf "${ENV_PERMANENT}" .env
        print_success "已链接配置文件"
    elif [ -f .env.template ]; then
        cp .env.template "${ENV_PERMANENT}"
        chmod 600 "${ENV_PERMANENT}"
        ln -sf "${ENV_PERMANENT}" .env
        print_warning "已创建配置模板，请稍后编辑"
    fi

    # 运行 setup.sh
    chmod +x setup.sh
    ./setup.sh

    # 安装服务
    sudo cp nautilus-trader.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable ${TRADER_SERVICE}
    sudo systemctl start ${TRADER_SERVICE}

    if systemctl is-active --quiet ${TRADER_SERVICE}.service; then
        print_success "AItrader 服务启动成功"
    else
        print_error "AItrader 服务启动失败"
    fi
fi

# ==================== Algvex Web 安装 ====================
if $INSTALL_WEB; then
    # 停止服务
    print_step "${STEP}/${TOTAL_STEPS}" "停止 Web 服务..."
    STEP=$((STEP + 1))

    sudo systemctl stop ${WEB_BACKEND_SERVICE} 2>/dev/null || true
    sudo systemctl stop ${WEB_FRONTEND_SERVICE} 2>/dev/null || true
    print_success "Web 服务已停止"

    # 清理并复制文件
    print_step "${STEP}/${TOTAL_STEPS}" "安装 Web 文件..."
    STEP=$((STEP + 1))

    rm -rf "${WEB_DIR}"
    mkdir -p "${WEB_DIR}"

    # 如果 AItrader 已安装，直接复制；否则临时克隆
    if [ -d "${INSTALL_DIR}/web" ]; then
        cp -r "${INSTALL_DIR}/web/backend" "${WEB_DIR}/"
        cp -r "${INSTALL_DIR}/web/frontend" "${WEB_DIR}/"
        cp -r "${INSTALL_DIR}/web/deploy" "${WEB_DIR}/"
    else
        TEMP_DIR="/tmp/aitrader-web-temp"
        rm -rf "${TEMP_DIR}"
        git clone -b "${BRANCH}" --depth 1 "${REPO_URL}" "${TEMP_DIR}"
        cp -r "${TEMP_DIR}/web/backend" "${WEB_DIR}/"
        cp -r "${TEMP_DIR}/web/frontend" "${WEB_DIR}/"
        cp -r "${TEMP_DIR}/web/deploy" "${WEB_DIR}/"
        rm -rf "${TEMP_DIR}"
    fi
    print_success "Web 文件已安装"

    # 恢复或创建配置
    if [ -f "/tmp/algvex-backend-env-backup" ]; then
        cp "/tmp/algvex-backend-env-backup" "${WEB_ENV}"
        rm -f "/tmp/algvex-backend-env-backup"
        print_success "已恢复 Web 配置"
    elif [ -f "${WEB_DIR}/backend/.env.example" ]; then
        # 首次安装：从模板创建并生成随机密钥
        cp "${WEB_DIR}/backend/.env.example" "${WEB_ENV}"
        # 生成随机 SECRET_KEY
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
        sed -i "s|your-secret-key-change-in-production|${SECRET_KEY}|g" "${WEB_ENV}"
        chmod 600 "${WEB_ENV}"
        print_warning "已创建 Web 配置模板，请编辑填入 Google OAuth 凭据"
        print_warning "  nano ${WEB_ENV}"
    else
        print_error "未找到 .env.example，请手动创建 ${WEB_ENV}"
    fi

    # 安装后端依赖
    print_step "${STEP}/${TOTAL_STEPS}" "安装 Web 后端依赖..."
    STEP=$((STEP + 1))

    cd "${WEB_DIR}/backend"
    python3.11 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    deactivate
    print_success "后端依赖已安装"

    # 安装前端依赖
    print_step "${STEP}/${TOTAL_STEPS}" "安装 Web 前端依赖..."
    STEP=$((STEP + 1))

    cd "${WEB_DIR}/frontend"
    npm install 2>&1 | tail -5 || { print_error "npm install 失败"; exit 1; }
    npm run build 2>&1 | tail -10 || { print_error "npm build 失败"; exit 1; }
    print_success "前端已构建"

    # 安装服务
    sudo cp "${WEB_DIR}/deploy/algvex-backend.service" /etc/systemd/system/
    sudo cp "${WEB_DIR}/deploy/algvex-frontend.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable ${WEB_BACKEND_SERVICE} ${WEB_FRONTEND_SERVICE}
    sudo systemctl start ${WEB_BACKEND_SERVICE} ${WEB_FRONTEND_SERVICE}

    if systemctl is-active --quiet ${WEB_BACKEND_SERVICE}; then
        print_success "Web 后端启动成功"
    else
        print_error "Web 后端启动失败"
    fi

    if systemctl is-active --quiet ${WEB_FRONTEND_SERVICE}; then
        print_success "Web 前端启动成功"
    else
        print_error "Web 前端启动失败"
    fi

    # 配置防火墙
    if command -v ufw &> /dev/null; then
        sudo ufw allow 80/tcp >/dev/null 2>&1 || true
        sudo ufw allow 443/tcp >/dev/null 2>&1 || true
        sudo ufw allow 3000/tcp >/dev/null 2>&1 || true
        sudo ufw allow 8000/tcp >/dev/null 2>&1 || true
    fi

    # 安装 Caddy (如果没有)
    if ! command -v caddy &> /dev/null; then
        print_warning "安装 Caddy..."
        sudo apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https 2>/dev/null || true
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null || true
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null 2>&1 || true
        sudo apt-get update -qq 2>/dev/null || true
        sudo apt-get install -y -qq caddy 2>/dev/null || true
    fi

    # 配置 Caddy (如果域名环境变量已设置)
    DOMAIN="${ALGVEX_DOMAIN:-}"
    if [ -n "$DOMAIN" ]; then
        print_warning "配置 Caddy for ${DOMAIN}..."
        sudo tee /etc/caddy/Caddyfile > /dev/null << CADDYEOF
${DOMAIN} {
    reverse_proxy /api/* localhost:8000
    reverse_proxy /* localhost:3000
}
CADDYEOF
        sudo systemctl restart caddy
        print_success "Caddy 已配置: ${DOMAIN}"
    else
        # 默认配置：使用 IP 访问
        IP=$(curl -s ifconfig.me 2>/dev/null || echo "localhost")
        sudo tee /etc/caddy/Caddyfile > /dev/null << CADDYEOF
:80 {
    reverse_proxy /api/* localhost:8000
    reverse_proxy /* localhost:3000
}
CADDYEOF
        sudo systemctl restart caddy 2>/dev/null || true
        print_success "Caddy 已配置 (HTTP 模式)"
        print_warning "设置域名: ALGVEX_DOMAIN=algvex.com ./reinstall.sh --web-only"
    fi
fi

# ==================== 完成 ====================
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                      ✅ 安装完成！                            ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 显示服务状态
echo -e "${CYAN}服务状态:${NC}"
if $INSTALL_TRADER; then
    STATUS=$(systemctl is-active ${TRADER_SERVICE} 2>/dev/null || echo "inactive")
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}●${NC} ${TRADER_SERVICE}: ${GREEN}运行中${NC}"
    else
        echo -e "  ${RED}●${NC} ${TRADER_SERVICE}: ${RED}未运行${NC}"
    fi
fi
if $INSTALL_WEB; then
    STATUS=$(systemctl is-active ${WEB_BACKEND_SERVICE} 2>/dev/null || echo "inactive")
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}●${NC} ${WEB_BACKEND_SERVICE}: ${GREEN}运行中${NC}"
    else
        echo -e "  ${RED}●${NC} ${WEB_BACKEND_SERVICE}: ${RED}未运行${NC}"
    fi
    STATUS=$(systemctl is-active ${WEB_FRONTEND_SERVICE} 2>/dev/null || echo "inactive")
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}●${NC} ${WEB_FRONTEND_SERVICE}: ${GREEN}运行中${NC}"
    else
        echo -e "  ${RED}●${NC} ${WEB_FRONTEND_SERVICE}: ${RED}未运行${NC}"
    fi
fi

# 显示访问地址
echo ""
echo -e "${CYAN}访问地址:${NC}"
if $INSTALL_WEB; then
    IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_IP")
    echo -e "  前端: ${YELLOW}http://${IP}:3000${NC}"
    echo -e "  后端: ${YELLOW}http://${IP}:8000/api/${NC}"
    echo -e "  管理: ${YELLOW}http://${IP}:3000/admin${NC}"
fi

# 显示配置提示
echo ""
echo -e "${CYAN}配置文件:${NC}"
if $INSTALL_TRADER; then
    echo -e "  AItrader: ${YELLOW}${ENV_PERMANENT}${NC}"
fi
if $INSTALL_WEB; then
    echo -e "  Web后端:  ${YELLOW}${WEB_ENV}${NC}"
fi

# 显示常用命令
echo ""
echo -e "${CYAN}常用命令:${NC}"
if $INSTALL_TRADER; then
    echo -e "  查看日志: ${YELLOW}sudo journalctl -u ${TRADER_SERVICE} -f --no-hostname${NC}"
fi
if $INSTALL_WEB; then
    echo -e "  Web日志:  ${YELLOW}sudo journalctl -u ${WEB_BACKEND_SERVICE} -f${NC}"
fi
echo -e "  诊断工具: ${YELLOW}cd ${INSTALL_DIR} && python3 diagnose.py${NC}"

# 待办提示
echo ""
echo -e "${YELLOW}待办事项:${NC}"
if $INSTALL_TRADER && [ ! -f "${ENV_PERMANENT}" ]; then
    echo -e "  1. 配置 AItrader API 密钥: nano ${ENV_PERMANENT}"
fi
if $INSTALL_WEB && [ ! -f "${WEB_ENV}" ]; then
    echo -e "  2. 配置 Web 后端: nano ${WEB_ENV}"
    echo -e "  3. 配置 Google OAuth 回调 URI"
    echo -e "  4. 配置域名 DNS 指向服务器"
fi
echo ""
