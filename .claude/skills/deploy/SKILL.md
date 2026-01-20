---
description: 部署交易机器人到服务器。用于更新代码、重启服务、检查状态。
---

# 部署交易机器人

## 关键信息
- **入口文件**: `main_live.py` (不是 main.py!)
- **服务器**: 139.180.157.152
- **用户**: linuxuser
- **路径**: /home/linuxuser/nautilus_AItrader
- **服务名**: nautilus-trader
- **分支**: claude/clone-nautilus-aitrader-SFBz9

## 部署步骤

1. 确保本地代码已提交并推送
2. 在服务器上执行:
```bash
cd /home/linuxuser/nautilus_AItrader
git pull origin claude/clone-nautilus-aitrader-SFBz9
sudo systemctl restart nautilus-trader
```

3. 验证部署:
```bash
sudo journalctl -u nautilus-trader -n 50 --no-hostname
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

- ❌ 使用 `main.py` → ✅ 使用 `main_live.py`
- ❌ 忘记 `AUTO_CONFIRM=true` → 会卡在确认提示
