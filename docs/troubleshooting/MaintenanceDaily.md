# 查看服务状态
sudo systemctl status deepseek-trader

# 停止服务
sudo systemctl stop deepseek-trader

# 启动服务
sudo systemctl start deepseek-trader

# 重启服务
sudo systemctl restart deepseek-trader

# 查看实时日志
sudo journalctl -u deepseek-trader -f

# 查看最近日志
tail -f /home/ubuntu/nautilus_deepseek/logs/trader.log

# 禁用开机自启
sudo systemctl disable deepseek-trader

# 启用开机自启
sudo systemctl enable deepseek-trader

监控建议
# 1. 实时监控日志
tail -f logs/trader.log | grep -E "DeepSeekAIStrategy|ERROR|WARN"

# 2. 查看 JSON 格式日志
tail -f DeepSeekTrader-001_*.json | jq -r '"\(.timestamp) [\(.level)] \(.component): \(.message)"'

# 3. 监控进程资源
watch -n 5 'ps aux | grep 121836'


重要提示：
以后如需修改 equity，有两个选择：
修改 start_trader.sh 和 restart_trader.sh 中的 export EQUITY=xxx
或创建 .env 文件设置 EQUITY=xxx
现在策略会使用 400 USDT 的实际余额进行交易。