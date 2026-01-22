#!/bin/bash
# ============================================================
# AItrader 一键清空重装脚本
#
# 用途: 完全清理并重新安装交易机器人
# 服务器: 139.180.157.152
# 用户: linuxuser
# 仓库: https://github.com/FelixWayne0318/AItrader
# 分支: claude/clone-nautilus-aitrader-SFBz9
#
# 使用方法:
#   方法1: 直接从 GitHub 下载并执行
#     curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/claude/clone-nautilus-aitrader-SFBz9/reinstall.sh | bash
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
BACKUP_DIR="/home/linuxuser"
REPO_URL="https://github.com/FelixWayne0318/AItrader.git"
BRANCH="claude/clone-nautilus-aitrader-SFBz9"
SERVICE_NAME="nautilus-trader"

echo ""
echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}   AItrader 一键清空重装脚本${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# ========== 第一步：备份 .env ==========
echo -e "${YELLOW}[1/8] 备份 API 密钥...${NC}"
ENV_BACKUP="${BACKUP_DIR}/env_backup_$(date +%Y%m%d_%H%M%S).txt"
if [ -f "${INSTALL_DIR}/.env" ]; then
    cp "${INSTALL_DIR}/.env" "${ENV_BACKUP}"
    cp "${INSTALL_DIR}/.env" "${BACKUP_DIR}/env_backup.txt"
    echo -e "${GREEN}✓ 已备份到 ${ENV_BACKUP}${NC}"
    echo -e "${GREEN}✓ 已备份到 ${BACKUP_DIR}/env_backup.txt${NC}"
else
    echo -e "${YELLOW}⚠ 未找到 .env 文件，跳过备份${NC}"
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

# ========== 第四步：克隆仓库 ==========
echo ""
echo -e "${YELLOW}[4/8] 克隆仓库...${NC}"
cd "${BACKUP_DIR}"
git clone -b "${BRANCH}" "${REPO_URL}" nautilus_AItrader
echo -e "${GREEN}✓ 仓库已克隆 (分支: ${BRANCH})${NC}"

# ========== 第五步：恢复 .env ==========
echo ""
echo -e "${YELLOW}[5/8] 恢复 .env 配置...${NC}"
cd "${INSTALL_DIR}"
if [ -f "${BACKUP_DIR}/env_backup.txt" ]; then
    cp "${BACKUP_DIR}/env_backup.txt" .env
    chmod 600 .env
    echo -e "${GREEN}✓ 已从备份恢复 .env${NC}"
else
    if [ -f .env.template ]; then
        cp .env.template .env
        chmod 600 .env
        echo -e "${YELLOW}⚠ 使用模板创建 .env，请稍后编辑填入 API 密钥:${NC}"
        echo -e "${YELLOW}  nano ${INSTALL_DIR}/.env${NC}"
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
echo -e "${BLUE}常用命令:${NC}"
echo -e "  查看日志:   ${YELLOW}sudo journalctl -u ${SERVICE_NAME} -f --no-hostname${NC}"
echo -e "  重启服务:   ${YELLOW}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  停止服务:   ${YELLOW}sudo systemctl stop ${SERVICE_NAME}${NC}"
echo -e "  全面诊断:   ${YELLOW}cd ${INSTALL_DIR} && python diagnose.py${NC}"
echo -e "  编辑密钥:   ${YELLOW}nano ${INSTALL_DIR}/.env${NC}"
echo ""
echo -e "${BLUE}安装路径:${NC} ${INSTALL_DIR}"
echo -e "${BLUE}服务名称:${NC} ${SERVICE_NAME}"
echo -e "${BLUE}分支:${NC} ${BRANCH}"
echo ""

# 提示查看日志
echo -e "${YELLOW}提示: 运行以下命令查看实时日志:${NC}"
echo -e "  sudo journalctl -u ${SERVICE_NAME} -f --no-hostname"
echo ""
