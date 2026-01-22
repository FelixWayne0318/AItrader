#!/bin/bash
# ============================================================
# AItrader 一键清空重装脚本
#
# 用途: 完全清理并重新安装交易机器人
# 服务器: 139.180.157.152
# 用户: linuxuser
# 仓库: https://github.com/FelixWayne0318/AItrader
# 分支: main
#
# .env 管理策略:
#   - 永久存储: ~/.env.aitrader (不会被删除)
#   - 项目目录: .env -> ~/.env.aitrader (软链接)
#   - 重装时自动保留配置
#
# 使用方法:
#   方法1: 直接从 GitHub 下载并执行
#     curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash
#
#   方法2: 本地执行
#     chmod +x reinstall.sh && ./reinstall.sh
#
# ============================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
INSTALL_DIR="/home/linuxuser/nautilus_AItrader"
HOME_DIR="/home/linuxuser"
ENV_PERMANENT="${HOME_DIR}/.env.aitrader"  # 永久存储位置
REPO_URL="https://github.com/FelixWayne0318/AItrader.git"
BRANCH="main"
SERVICE_NAME="nautilus-trader"

echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}   AItrader 一键清空重装脚本${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# ========== 第一步：处理 .env 配置 ==========
echo -e "${YELLOW}[1/8] 处理 .env 配置...${NC}"

# 检查是否已有永久配置
if [ -f "${ENV_PERMANENT}" ]; then
    echo -e "${GREEN}✓ 发现永久配置文件: ${ENV_PERMANENT}${NC}"
    echo -e "${GREEN}  (重装不会影响此文件)${NC}"
else
    # 检查项目目录中是否有 .env (非软链接)
    if [ -f "${INSTALL_DIR}/.env" ] && [ ! -L "${INSTALL_DIR}/.env" ]; then
        echo -e "${YELLOW}  迁移现有 .env 到永久位置...${NC}"
        cp "${INSTALL_DIR}/.env" "${ENV_PERMANENT}"
        chmod 600 "${ENV_PERMANENT}"
        echo -e "${GREEN}✓ 已迁移到 ${ENV_PERMANENT}${NC}"
    else
        echo -e "${YELLOW}⚠ 未找到现有配置，稍后需要手动配置${NC}"
    fi
fi

# ========== 第二步：停止并清理旧服务 ==========
echo ""
echo -e "${YELLOW}[2/8] 停止并清理旧服务...${NC}"

# 停止 nautilus-trader 服务
if systemctl is-active --quiet ${SERVICE_NAME}.service 2>/dev/null; then
    sudo systemctl stop ${SERVICE_NAME}.service
    echo -e "${GREEN}✓ 已停止 ${SERVICE_NAME} 服务${NC}"
fi
sudo systemctl disable ${SERVICE_NAME}.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/${SERVICE_NAME}.service 2>/dev/null || true

# 停止旧的 deepseek-trader 服务（如果存在）
if systemctl is-active --quiet deepseek-trader.service 2>/dev/null; then
    sudo systemctl stop deepseek-trader.service
fi
sudo systemctl disable deepseek-trader.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/deepseek-trader.service 2>/dev/null || true

# 重新加载 systemd
sudo systemctl daemon-reload

# 杀死所有可能残留的进程
pkill -f "main_live.py" 2>/dev/null || true
pkill -f "nautilus_AItrader" 2>/dev/null || true
sleep 2

# 强制杀死残留进程
pkill -9 -f "main_live.py" 2>/dev/null || true
sleep 1

echo -e "${GREEN}✓ 旧服务已清理${NC}"

# ========== 第三步：删除旧目录 ==========
echo ""
echo -e "${YELLOW}[3/8] 删除旧目录...${NC}"
rm -rf "${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}_backup"
echo -e "${GREEN}✓ 旧目录已删除${NC}"
echo -e "${GREEN}  (永久配置 ${ENV_PERMANENT} 保持不变)${NC}"

# ========== 第四步：克隆仓库 ==========
echo ""
echo -e "${YELLOW}[4/8] 克隆仓库...${NC}"
cd "${HOME_DIR}"
git clone -b "${BRANCH}" "${REPO_URL}" nautilus_AItrader
echo -e "${GREEN}✓ 仓库已克隆 (分支: ${BRANCH})${NC}"

# ========== 第五步：配置 .env 软链接 ==========
echo ""
echo -e "${YELLOW}[5/8] 配置 .env...${NC}"
cd "${INSTALL_DIR}"

# 删除克隆时可能带来的 .env 或 .env.template
rm -f .env 2>/dev/null || true

if [ -f "${ENV_PERMANENT}" ]; then
    # 创建软链接
    ln -sf "${ENV_PERMANENT}" .env
    echo -e "${GREEN}✓ 已创建软链接: .env -> ${ENV_PERMANENT}${NC}"
else
    # 首次安装，从模板创建
    if [ -f .env.template ]; then
        cp .env.template "${ENV_PERMANENT}"
        chmod 600 "${ENV_PERMANENT}"
        ln -sf "${ENV_PERMANENT}" .env
        echo -e "${YELLOW}⚠ 首次安装，已从模板创建配置${NC}"
        echo -e "${YELLOW}  请编辑 ${ENV_PERMANENT} 填入 API 密钥${NC}"
    else
        echo -e "${RED}✗ 未找到 .env.template${NC}"
    fi
fi

# ========== 第六步：运行 setup.sh ==========
echo ""
echo -e "${YELLOW}[6/8] 运行部署脚本...${NC}"
chmod +x setup.sh
./setup.sh

# ========== 第七步：安装 systemd 服务 ==========
echo ""
echo -e "${YELLOW}[7/8] 安装 systemd 服务...${NC}"
sudo cp nautilus-trader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
echo -e "${GREEN}✓ systemd 服务已安装${NC}"

# ========== 第八步：启动服务并验证 ==========
echo ""
echo -e "${YELLOW}[8/8] 启动服务并验证...${NC}"
sudo systemctl start ${SERVICE_NAME}
sleep 3

# 检查服务状态
if systemctl is-active --quiet ${SERVICE_NAME}.service; then
    echo -e "${GREEN}✓ 服务启动成功${NC}"
else
    echo -e "${RED}✗ 服务启动失败，请检查日志${NC}"
    echo -e "${YELLOW}  sudo journalctl -u ${SERVICE_NAME} -n 50 --no-pager${NC}"
fi

# 显示服务状态
echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}   服务状态${NC}"
echo -e "${BLUE}==========================================${NC}"
sudo systemctl status ${SERVICE_NAME} --no-pager -l || true

# ========== 完成 ==========
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}   ✅ 安装完成！${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo -e "${BLUE}配置文件位置:${NC}"
echo -e "  永久存储: ${YELLOW}${ENV_PERMANENT}${NC}"
echo -e "  软链接:   ${YELLOW}${INSTALL_DIR}/.env -> ${ENV_PERMANENT}${NC}"
echo ""
echo -e "${BLUE}常用命令:${NC}"
echo -e "  查看日志:   ${YELLOW}sudo journalctl -u ${SERVICE_NAME} -f --no-hostname${NC}"
echo -e "  重启服务:   ${YELLOW}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  停止服务:   ${YELLOW}sudo systemctl stop ${SERVICE_NAME}${NC}"
echo -e "  全面诊断:   ${YELLOW}cd ${INSTALL_DIR} && python diagnose.py${NC}"
echo -e "  编辑密钥:   ${YELLOW}nano ${ENV_PERMANENT}${NC}"
echo ""
echo -e "${BLUE}安装路径:${NC} ${INSTALL_DIR}"
echo -e "${BLUE}服务名称:${NC} ${SERVICE_NAME}"
echo -e "${BLUE}分支:${NC} ${BRANCH}"
echo ""

# 检查是否需要配置
if [ -f "${ENV_PERMANENT}" ]; then
    # 检查是否有有效的 API 密钥
    if grep -E -q "^BINANCE_API_KEY=.+" "${ENV_PERMANENT}" 2>/dev/null; then
        echo -e "${GREEN}✓ API 密钥已配置${NC}"
    else
        echo -e "${YELLOW}⚠ 请编辑配置文件填入 API 密钥:${NC}"
        echo -e "  ${YELLOW}nano ${ENV_PERMANENT}${NC}"
        echo ""
    fi
fi

echo -e "${YELLOW}提示: 运行以下命令查看实时日志:${NC}"
echo -e "  sudo journalctl -u ${SERVICE_NAME} -f --no-hostname"
echo ""
