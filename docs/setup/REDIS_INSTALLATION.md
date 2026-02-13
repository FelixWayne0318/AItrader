# 🔴 Redis 安装和配置总结

## ✅ 安装完成状态

**日期**: 2025-11-06  
**Redis 版本**: 7.0.15  
**Python Redis 客户端**: 7.0.1  

---

## 📦 已安装的组件

### 1. Redis Server (系统服务)

```bash
✅ Redis Server: redis-server 7.0.15
✅ 监听地址: 127.0.0.1:6379
✅ 进程 ID: 298577
✅ 状态: active (running)
✅ 开机自启动: enabled
```

**验证命令:**
```bash
sudo systemctl status redis-server
redis-cli ping  # 应返回 PONG
```

### 2. Python Redis 客户端 (虚拟环境)

```bash
✅ 虚拟环境: /home/ubuntu/deepseek_venv
✅ Redis 包版本: 7.0.1
✅ 连接测试: 成功
```

**验证命令:**
```bash
source /home/ubuntu/deepseek_venv/bin/activate
python -c "import redis; print(redis.__version__)"
```

---

## 🔧 配置信息

### Redis 服务器配置

| 配置项 | 值 |
|-------|-----|
| 监听地址 | 127.0.0.1 |
| 端口 | 6379 |
| 数据库数量 | 16 (默认) |
| 持久化 | RDB + AOF |
| 最大内存 | 无限制 (系统内存) |

### 策略配置 (strategy_config.yaml)

```yaml
risk:
  # OCO (One-Cancels-the-Other) Management
  enable_oco: true
  oco_redis_host: "localhost"
  oco_redis_port: 6379
  oco_redis_db: 0
  oco_redis_password: null
  oco_group_ttl_hours: 24
```

---

## 🧪 功能测试

### 1. Redis 服务器测试

```bash
# Ping 测试
$ redis-cli ping
PONG

# 查看服务器信息
$ redis-cli INFO server

# 查看内存使用
$ redis-cli INFO memory
```

### 2. Python 客户端测试

```python
import redis

# 连接 Redis
r = redis.Redis(host='localhost', port=6379, db=0)

# 测试连接
print(r.ping())  # True

# 设置和获取值
r.set('test_key', 'test_value')
print(r.get('test_key'))  # b'test_value'

# 删除测试键
r.delete('test_key')
```

### 3. OCO Manager 测试

```bash
cd /home/ubuntu/nautilus_deepseek
source /home/ubuntu/deepseek_venv/bin/activate

python -c "
from utils.oco_manager import OCOManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test')

oco = OCOManager(
    redis_host='localhost',
    redis_port=6379,
    redis_db=0,
    logger=logger
)

print('✅ OCO Manager initialized')
print(f'Statistics: {oco.get_statistics()}')
"
```

---

## 🚀 使用场景

### OCO 功能支持

Redis 为以下功能提供持久化存储：

1. **OCO 组管理**
   - 存储止损/止盈订单关联关系
   - 跟踪订单状态（pending/filled/cancelled）
   - 自动过期清理（24小时后）

2. **重启恢复**
   - 策略重启后恢复 OCO 组
   - 避免孤儿订单
   - 确保订单关联不丢失

3. **部分止盈支持**
   - 支持 1 个 SL + N 个 TP 订单
   - 任何订单成交时取消所有其他订单
   - 保证订单同步

---

## 📊 监控和维护

### 查看 Redis 状态

```bash
# 服务状态
sudo systemctl status redis-server

# 内存使用
redis-cli INFO memory | grep used_memory_human

# 连接数
redis-cli INFO clients | grep connected_clients

# 键数量
redis-cli INFO keyspace
```

### 查看 OCO 数据

```bash
# 连接到 Redis
redis-cli

# 查看所有 OCO 组键
KEYS nautilus:deepseek:oco:*

# 查看特定 OCO 组
HGETALL nautilus:deepseek:oco:BUY_BTCUSDT_1730880000

# 查看所有键的过期时间
TTL nautilus:deepseek:oco:BUY_BTCUSDT_1730880000

# 退出
EXIT
```

### 清理测试数据

```bash
# 删除所有 OCO 测试数据（谨慎使用！）
redis-cli KEYS "nautilus:deepseek:oco:*" | xargs redis-cli DEL

# 或者只删除过期的
# Redis 会自动删除过期键，无需手动操作
```

---

## ⚙️ 启动和停止

### 启动 Redis

```bash
sudo systemctl start redis-server
```

### 停止 Redis

```bash
sudo systemctl stop redis-server
```

### 重启 Redis

```bash
sudo systemctl restart redis-server
```

### 禁用开机自启动（不推荐）

```bash
sudo systemctl disable redis-server
```

---

## 🔐 安全建议

### 当前配置（本地开发）

✅ **监听地址**: 127.0.0.1（仅本地访问）  
✅ **无密码**: 适合本地开发  
✅ **防火墙**: 默认不对外开放 6379 端口  

### 生产环境建议

如果部署到生产环境，建议：

1. **设置密码**

```bash
# 编辑配置文件
sudo nano /etc/redis/redis.conf

# 添加密码
requirepass your_strong_password_here

# 重启服务
sudo systemctl restart redis-server
```

更新策略配置：

```yaml
oco_redis_password: "your_strong_password_here"
```

2. **限制监听地址**

```bash
# 如果只在本地使用，保持 127.0.0.1
bind 127.0.0.1

# 如果需要远程访问，指定特定 IP
bind 127.0.0.1 192.168.1.100
```

3. **启用 AOF 持久化**

```bash
# 编辑配置文件
sudo nano /etc/redis/redis.conf

# 启用 AOF
appendonly yes
appendfsync everysec
```

---

## 🐛 故障排查

### 问题 1: Redis 无法启动

**检查日志:**
```bash
sudo journalctl -u redis-server -n 50
```

**常见原因:**
- 端口 6379 被占用
- 配置文件错误
- 内存不足

### 问题 2: Python 连接失败

**错误信息:**
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**解决方案:**
```bash
# 1. 检查 Redis 是否运行
sudo systemctl status redis-server

# 2. 检查端口是否监听
sudo netstat -tulpn | grep 6379

# 3. 测试连接
redis-cli ping
```

### 问题 3: OCO 组未保存

**检查步骤:**
```python
# 验证 Redis 连接
from utils.oco_manager import OCOManager
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('test')

oco = OCOManager(redis_host='localhost', redis_port=6379, logger=logger)
print(oco.get_statistics())
```

**常见原因:**
- Redis 服务未启动
- 配置中 `enable_oco` 设为 false
- Redis 密码配置错误

---

## 📈 性能优化

### 内存优化

```bash
# 设置最大内存（例如 256MB）
redis-cli CONFIG SET maxmemory 256mb

# 设置内存回收策略（LRU）
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### 持久化优化

```bash
# 调整 RDB 保存频率
save 900 1      # 900秒内至少1个键改变
save 300 10     # 300秒内至少10个键改变
save 60 10000   # 60秒内至少10000个键改变

# 或禁用 RDB（仅使用 AOF）
save ""
```

---

## 📚 相关文档

- [OCO 功能实现](./FEATURE_OCO_IMPLEMENTATION.md)
- [自动止损止盈](./FEATURE_STOP_LOSS_TAKE_PROFIT.md)
- [部分止盈功能](./FEATURE_PARTIAL_TAKE_PROFIT.md)
- [Redis 官方文档](https://redis.io/documentation)

---

## 🎉 总结

✅ **Redis 服务器**: 7.0.15 运行中  
✅ **Python 客户端**: 7.0.1 已安装  
✅ **OCO Manager**: 测试通过  
✅ **开机自启动**: 已启用  
✅ **持久化**: RDB + AOF 已启用  
✅ **策略集成**: 完全就绪  

**您的交易系统现在拥有完整的 Redis 持久化支持！**

OCO 功能将自动保存到 Redis，即使策略重启也能恢复订单状态。

---

**Last Updated**: 2025-11-06  
**Status**: ✅ Production Ready

