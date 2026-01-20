---
name: server-status
description: 检查服务器状态和交易机器人运行情况。Use when checking server status, bot health, viewing logs, or monitoring the trading system.
allowed-tools:
  - Bash
  - Read
---

# 检查服务器状态

## 服务器信息

| 项目 | 值 |
|------|-----|
| **IP** | 139.180.157.152 |
| **用户** | linuxuser |
| **服务名** | nautilus-trader |
| **路径** | /home/linuxuser/nautilus_AItrader |

## 检查命令

### 服务状态
```bash
sudo systemctl status nautilus-trader
```

### 查看日志
```bash
# 最近50行
sudo journalctl -u nautilus-trader -n 50 --no-hostname

# 实时跟踪
sudo journalctl -u nautilus-trader -f --no-hostname
```

### 检查进程
```bash
ps aux | grep main_live.py
```

## 状态判断

### ✅ 正常运行标志
```
🚀 *Strategy Started*
📊 *Instrument*: BTCUSDT-PERP
Active: active (running)
```

### ❌ 常见错误

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `can't open file 'main.py'` | 入口文件错误 | ExecStart 改为 `main_live.py` |
| `EOFError: EOF when reading a line` | 缺少确认环境变量 | 添加 `Environment=AUTO_CONFIRM=true` |
| `telegram.error.Conflict` | Telegram 冲突 | 不影响交易，可忽略 |

## 快速诊断

如果服务异常，按以下顺序检查：

1. **服务状态**: `sudo systemctl status nautilus-trader`
2. **最近日志**: `sudo journalctl -u nautilus-trader -n 100 --no-hostname`
3. **配置文件**: `cat /etc/systemd/system/nautilus-trader.service`
4. **入口文件**: 确认是 `main_live.py`
