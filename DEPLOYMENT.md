# 部署指南

## 关键信息

| 项目 | 值 |
|------|-----|
| 入口文件 | `main_live.py` (不是 main.py) |
| 服务器 | 139.180.157.152 |
| 用户名 | linuxuser |
| 安装路径 | /home/linuxuser/nautilus_AItrader |
| 服务名 | nautilus-trader |
| 分支 | claude/clone-nautilus-aitrader-SFBz9 |

## 同步代码到服务器

### 方法一：快速同步（推荐）

```bash
# 在服务器上执行，强制覆盖本地修改
cd /home/linuxuser/nautilus_AItrader
git fetch origin claude/clone-nautilus-aitrader-SFBz9
git reset --hard origin/claude/clone-nautilus-aitrader-SFBz9
sudo systemctl restart nautilus-trader
```

### 方法二：使用同步脚本

```bash
# 交互式同步（会询问确认）
./scripts/sync_from_repo.sh

# 快速同步（无需确认）
./scripts/quick_sync.sh
```

### 方法三：普通更新（有本地修改时可能失败）

```bash
cd /home/linuxuser/nautilus_AItrader
git pull origin claude/clone-nautilus-aitrader-SFBz9
sudo systemctl restart nautilus-trader
```

## 常用命令

```bash
# 查看状态
sudo systemctl status nautilus-trader

# 重启服务
sudo systemctl restart nautilus-trader

# 查看日志
sudo journalctl -u nautilus-trader -f --no-hostname

# 查看最近50行日志
sudo journalctl -u nautilus-trader -n 50 --no-hostname
```

## systemd 服务配置

```bash
sudo tee /etc/systemd/system/nautilus-trader.service << 'EOF'
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable nautilus-trader
sudo systemctl start nautilus-trader
```

## 已修复的问题

1. **止损Bug** (commit 7f940fb)
   - 问题：止损价格可能在入场价错误一侧
   - 修复：添加验证确保止损在正确方向

2. **CryptoOracle API** (commit 07cd27f)
   - 问题：API key 失效
   - 修复：替换为 Binance 多空比 API

## 测试修复

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate
python test_sl_fix.py
```

## 环境变量 (.env)

```
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
DEEPSEEK_API_KEY=xxx
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

## 注意事项

- 入口是 `main_live.py`，不是 `main.py`
- 需要设置 `AUTO_CONFIRM=true` 跳过确认提示
- Telegram 命令有冲突问题（不影响交易）
