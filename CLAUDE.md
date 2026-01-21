# AItrader - NautilusTrader DeepSeek 交易机器人

## 项目概述
基于 NautilusTrader 框架的 AI 驱动加密货币交易系统，使用 DeepSeek AI 进行信号生成。

## ⚠️ 关键信息

| 项目 | 值 |
|------|-----|
| **入口文件** | `main_live.py` (不是 main.py!) |
| **服务器 IP** | 139.180.157.152 |
| **用户名** | linuxuser |
| **安装路径** | /home/linuxuser/nautilus_AItrader |
| **服务名** | nautilus-trader |
| **分支** | claude/clone-nautilus-aitrader-SFBz9 |

## 常用命令

```bash
# 服务器操作
sudo systemctl restart nautilus-trader
sudo journalctl -u nautilus-trader -f --no-hostname

# 更新代码
cd /home/linuxuser/nautilus_AItrader
git pull origin claude/clone-nautilus-aitrader-SFBz9
sudo systemctl restart nautilus-trader

# 测试修复
python test_sl_fix.py
```

## systemd 服务配置

```ini
[Service]
ExecStart=/home/linuxuser/nautilus_AItrader/venv/bin/python main_live.py
Environment=AUTO_CONFIRM=true
```

## 已修复的问题

1. **止损Bug** (commit 7f940fb)
   - 问题：止损价格可能在入场价错误一侧
   - 修复：添加验证确保 LONG 止损 < 入场价，SHORT 止损 > 入场价

2. **CryptoOracle API** (commit 07cd27f)
   - 问题：API key 失效
   - 修复：替换为 Binance 多空比 API

3. **Binance POSITION_RISK_CONTROL** (commit 1ed1357)
   - 问题：Binance 新增 filter type，NautilusTrader 1.202.0 不支持
   - 错误：`msgspec.ValidationError: Invalid enum value 'POSITION_RISK_CONTROL'`
   - 修复：添加 `_missing_` 钩子动态处理未知枚举值
   - 文件：`patches/binance_enums.py`
   - 参考：[msgspec 官方方案](https://github.com/jcrist/msgspec/issues/531)

## 常见错误避免

- ❌ 使用 `main.py` 作为入口 → ✅ 使用 `main_live.py`
- ❌ 忘记设置 `AUTO_CONFIRM=true` → 会卡在确认提示
- ❌ 止损在入场价错误一侧 → 已修复，会自动回退到默认2%

## 文件结构

```
/home/user/AItrader/
├── main_live.py          # 入口文件
├── strategy/
│   └── deepseek_strategy.py  # 主策略 (含止损修复)
├── utils/
│   ├── deepseek_client.py    # DeepSeek AI 客户端
│   └── sentiment_client.py   # Binance 多空比 (替代 CryptoOracle)
├── patches/
│   └── binance_enums.py      # Binance枚举兼容性补丁
├── configs/
│   └── strategy_config.yaml  # 策略配置
├── test_sl_fix.py        # 止损修复测试
├── test_binance_patch.py # 枚举补丁测试
├── DEPLOYMENT.md         # 部署指南
└── README.md             # 项目文档
```

## API 密钥 (保存在 .env)

```
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
DEEPSEEK_API_KEY=xxx
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

## 联系方式

- GitHub: FelixWayne0318
- 仓库: https://github.com/FelixWayne0318/AItrader
