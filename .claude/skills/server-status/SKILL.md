---
description: 检查服务器状态和交易机器人运行情况。
---

# 检查服务器状态

## 服务器信息
- **IP**: 139.180.157.152
- **用户**: linuxuser
- **服务名**: nautilus-trader

## 检查命令

### 1. 服务状态
```bash
sudo systemctl status nautilus-trader
```

### 2. 查看日志
```bash
# 最近50行
sudo journalctl -u nautilus-trader -n 50 --no-hostname

# 实时跟踪
sudo journalctl -u nautilus-trader -f --no-hostname
```

### 3. 检查进程
```bash
ps aux | grep main_live.py
```

### 4. 检查端口
```bash
netstat -tlnp | grep python
```

## 常见状态

### ✅ 正常运行
```
🚀 *Strategy Started*
📊 *Instrument*: BTCUSDT-PERP
```

### ❌ 入口文件错误
```
can't open file 'main.py': No such file or directory
```
**解决**: 确保 ExecStart 使用 `main_live.py`

### ❌ 确认提示卡住
```
Are you sure you want to continue? (yes/no):
EOFError: EOF when reading a line
```
**解决**: 添加 `Environment=AUTO_CONFIRM=true`

### ⚠️ Telegram 冲突
```
telegram.error.Conflict: terminated by other...
```
**说明**: 不影响交易，只是 Telegram 命令监听有问题
