---
name: deploy
description: 部署交易机器人到服务器。用于更新代码、重启服务、检查状态。Use when deploying, updating code, restarting service, or checking deployment status.
allowed-tools:
  - Bash
  - Read
  - Grep
---

# 部署交易机器人

## 关键信息

| 项目 | 值 |
|------|-----|
| **入口文件** | `main_live.py` (不是 main.py!) |
| **服务器** | 139.180.157.152 |
| **用户** | linuxuser |
| **路径** | /home/linuxuser/nautilus_AItrader |
| **服务名** | nautilus-trader |
| **分支** | claude/clone-nautilus-aitrader-SFBz9 |

## 部署命令

如果用户提供了参数，执行对应操作：
- `$ARGUMENTS` 包含 "restart" → 重启服务
- `$ARGUMENTS` 包含 "status" → 检查状态
- `$ARGUMENTS` 包含 "update" → 更新代码并重启
- 无参数 → 显示部署信息

### 更新代码并重启
```bash
cd /home/linuxuser/nautilus_AItrader
git pull origin claude/clone-nautilus-aitrader-SFBz9
sudo systemctl restart nautilus-trader
```

### 检查状态
```bash
sudo systemctl status nautilus-trader
sudo journalctl -u nautilus-trader -n 30 --no-hostname
```

## systemd 服务配置

```ini
[Unit]
Description=Nautilus AITrader Bot
After=network.target

[Service]
Type=simple
User=linuxuser
WorkingDirectory=/home/linuxuser/nautilus_AItrader
ExecStart=/home/linuxuser/nautilus_AItrader/venv/bin/python main_live.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=AUTO_CONFIRM=true

[Install]
WantedBy=multi-user.target
```

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `can't open file 'main.py'` | 入口文件错误 | 使用 `main_live.py` |
| `EOFError: EOF when reading a line` | 缺少 AUTO_CONFIRM | 添加 `Environment=AUTO_CONFIRM=true` |
| 服务不断重启 | 配置错误 | 检查 ExecStart 路径 |
