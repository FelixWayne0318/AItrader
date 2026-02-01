# AItrader - NautilusTrader DeepSeek 交易机器人

## 项目概述
基于 NautilusTrader 框架的 AI 驱动加密货币交易系统，使用 DeepSeek AI 进行信号生成。

## 🚨 代码修改规范 (必读)

在修改任何代码之前，**必须**按以下顺序调研：

1. **官方文档** - NautilusTrader、python-telegram-bot 等框架的官方文档
2. **社区/GitHub Issues** - 查看是否有相关问题和解决方案
3. **原始仓库** - 对比 [Patrick-code-Bot/nautilus_AItrader](https://github.com/Patrick-code-Bot/nautilus_AItrader) 的实现
4. **提出方案** - 基于以上调研，结合当前系统问题，提出合理修改方案

**禁止**：
- ❌ 凭猜测直接修改代码
- ❌ 未经调研就"优化"或"改进"代码
- ❌ 忽略原始仓库的已验证实现
- ❌ 不了解框架线程模型就修改异步/多线程代码

**教训案例**：
- 将 `nautilus_trader.indicators` (Cython) 改为 `nautilus_trader.core.nautilus_pyo3` (Rust) 导致线程安全 panic
- 未研究 python-telegram-bot v20 的异步模型就混合使用 asyncio/threading

**修改后必须运行**：
```bash
# 智能回归检测 (规则自动从 git 历史生成，零维护)
python3 scripts/smart_commit_analyzer.py

# 预期结果: ✅ 所有规则验证通过
# 如果有 ❌ 失败项，检查是否引入了回归
```

## 📋 配置管理规范 (必读)

本项目采用**统一配置管理**，禁止硬编码参数。所有可配置的值都必须通过 ConfigManager 管理。

### 配置分层架构原则

基于 [12-Factor App](https://12factor.net/config) 和业界最佳实践，本项目采用**严格分层**的配置架构：

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: 代码中的常量 (不变的业务逻辑规则)                          │
│  ├─ CONFIDENCE_WEIGHT = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}         │
│  ├─ VALID_SIGNALS = {'BUY', 'SELL', 'HOLD'}                        │
│  └─ 这些是业务规则，不是配置，不应该被修改                           │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: configs/base.yaml (所有业务参数的单一来源)                 │
│  ├─ 止损/止盈比例、仓位大小、杠杆倍数                               │
│  ├─ 技术指标周期 (SMA, RSI, MACD, BB)                              │
│  ├─ AI 参数 (temperature, model, retry_delay)                      │
│  ├─ 网络参数 (timeout, cache_ttl)                                  │
│  └─ 所有可调业务参数都必须在这里定义                                │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: configs/{env}.yaml (环境覆盖)                             │
│  ├─ production.yaml: timer=900s, log=INFO                          │
│  ├─ development.yaml: timer=60s, log=DEBUG, 短周期指标参数          │
│  └─ backtest.yaml: telegram=false, use_real_balance=false          │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 4: ~/.env.aitrader (仅敏感信息)                              │
│  ├─ BINANCE_API_KEY, BINANCE_API_SECRET                            │
│  ├─ DEEPSEEK_API_KEY                                               │
│  ├─ TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID                           │
│  │                                                                  │
│  │  ⚠️ 禁止在此文件中放置业务参数！                                 │
│  │  ❌ 不要: EQUITY, LEVERAGE, BASE_POSITION_USDT                  │
│  │  ❌ 不要: TIMER_INTERVAL_SEC, LOG_LEVEL                         │
│  └─ 这些应该在 YAML 配置文件中管理                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 配置来源优先级 (严格执行)

| 数据类型 | 正确来源 | 错误做法 |
|---------|---------|---------|
| **敏感信息** (API keys) | `~/.env.aitrader` | ❌ 写在代码或 YAML 中 |
| **业务参数** (止损比例等) | `configs/*.yaml` | ❌ 环境变量或代码硬编码 |
| **环境差异** (日志级别等) | `configs/{env}.yaml` | ❌ 在代码中 if/else 判断 |
| **业务规则常量** | 代码中 | ❌ 放在配置文件中 |

**参考资料**:
- [12-Factor App Config](https://12factor.net/config)
- [Python Configuration Best Practices 2025](https://toxigon.com/best-practices-for-python-configuration-management)
- [Dynaconf Documentation](https://www.dynaconf.com/)

### 必须配置化的参数类型

✅ **必须配置化** (禁止硬编码):

1. **业务参数**
   - 交易相关: 止损百分比、止盈比例、最小交易金额、杠杆倍数
   - AI 参数: 模型名称、温度参数、重试延迟、超时时间
   - 风险管理: RSI 阈值、仓位比例、信心阈值

2. **网络参数**
   - API 超时时间、重试次数、连接延迟
   - Telegram 启动延迟、轮询间隔
   - Binance API recv_window、缓存 TTL

3. **环境差异参数**
   - 日志级别 (DEBUG/INFO)
   - 定时器间隔 (开发: 1分钟, 生产: 15分钟)
   - 测试模式标志

⚠️ **可以硬编码** (但需谨慎):
- 逻辑常量 (如 `CONFIDENCE_LEVELS = {'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}`)
- 框架固定值 (如 NautilusTrader 的 enum 值)
- 单位换算常量 (如 `SECONDS_PER_MINUTE = 60`)

❌ **禁止硬编码** (常见错误):

```python
# ❌ 错误示例
timeout = 10  # 应该从配置读取
retry_delay = 1.0  # 应该从配置读取
min_trade_amount = 100  # 应该从配置读取

# ✅ 正确示例
timeout = config.get('sentiment', 'timeout', default=10)
retry_delay = config.get('ai', 'deepseek', 'retry_delay', default=1.0)
min_trade_amount = config.get('trading_logic', 'min_notional_usdt', default=100)
```

### 新增功能配置化检查清单

当添加新功能或修改现有代码时，**必须**完成以下检查：

- [ ] 识别所有可能需要调整的数值参数
- [ ] 在 `configs/base.yaml` 中添加配置定义
- [ ] 在 `strategy/deepseek_strategy.py` 的 dataclass 中添加字段（如需）
- [ ] 在 `main_live.py` 中从 ConfigManager 加载参数
- [ ] 传递参数到相关类/函数
- [ ] 更新 `CLAUDE.md` 的配置参数表格
- [ ] 运行 `python3 scripts/validate_path_aliases.py` 验证配置路径
- [ ] 运行 `python3 main_live.py --env development --dry-run` 验证配置加载

### 配置化最佳实践

1. **参数分组**: 按功能分类放置 (ai.*, risk.*, network.*, etc.)
2. **合理默认值**: 所有配置项都应提供安全的默认值
3. **环境差异**: 开发/生产环境不同的值放在对应的 .yaml 文件
4. **敏感信息**: API keys 等敏感信息放在 `~/.env.aitrader`
5. **向后兼容**: 使用 PATH_ALIASES 支持旧配置路径

### 代码审查检查点

审查代码时，重点检查：

- 是否存在魔法数字 (magic numbers)
- 是否存在硬编码的字符串 (API 端点、模型名称等)
- 新增的配置项是否有文档说明
- 是否提供了合理的默认值
- 参数传递链是否完整 (ConfigManager → main_live.py → strategy dataclass → utils 类)

### 违反规范的处理

如果发现硬编码参数：

1. 在 Code Review 中明确指出
2. 要求开发者迁移到 ConfigManager
3. 运行以下命令查找潜在硬编码：
   ```bash
   # 查找数值型硬编码
   grep -rn "= [0-9]\+\.[0-9]\+" --include="*.py" | grep -v test | grep -v __pycache__

   # 查找字符串型硬编码（API 端点等）
   grep -rn "https://\|http://" --include="*.py" | grep -v test
   ```

### 参考文档

- 完整配置管理方案: `docs/CONFIG_MANAGEMENT_PROPOSAL.md`
- 配置验证脚本: `scripts/validate_path_aliases.py`
- 性能基准测试: `scripts/benchmark_config.py`
- 循环导入检测: `scripts/check_circular_imports.sh`
- 全面诊断脚本: `scripts/comprehensive_diagnosis.py`

### 提交分析工具 (自动化回归检测)

| 工具 | 功能 | 运行方式 |
|------|------|----------|
| **smart_commit_analyzer.py** | 智能回归检测 (规则自动从 git 生成) | `python3 scripts/smart_commit_analyzer.py` |
| **analyze_commits_ai.py** | AI 深度语义分析 (需要 DEEPSEEK_API_KEY) | `python3 scripts/analyze_commits_ai.py` |
| **analyze_dependencies.py** | Python AST 依赖分析 (循环依赖/缺失模块) | `python3 scripts/analyze_dependencies.py` |
| **analyze_git_changes.py** | Git 历史分析 (提交类型统计) | `python3 scripts/analyze_git_changes.py` |
| **validate_commit_fixes.py** | 旧版手动规则检查 (已被 smart 替代) | `python3 scripts/validate_commit_fixes.py` |

**GitHub Actions 自动运行**: 每次 push/PR 自动触发 `.github/workflows/commit-analysis.yml`

### CodeQL 代码分析

CodeQL 提供更深入的语义分析，包括安全漏洞检测和数据流分析。

```bash
# GitHub Actions 自动运行 (每周一 + 每次 push 到 main)
# 配置文件: .github/workflows/codeql-analysis.yml

# 自定义查询 (检测特定模式)
.github/codeql/custom-queries/find-imports.ql      # 追踪所有 import 语句
.github/codeql/custom-queries/hardcoded-paths.ql   # 检测硬编码文件路径
```

**CodeQL vs analyze_dependencies.py**:
| 特性 | CodeQL | analyze_dependencies.py |
|------|--------|------------------------|
| 运行速度 | 较慢 (需构建数据库) | 快速 (直接 AST 解析) |
| 分析深度 | 完整数据流/污点分析 | import 依赖关系 |
| 安全检测 | SQL注入、命令注入等 | 无 |
| 自定义查询 | QL 语言 | Python 代码 |
| 本地运行 | 需安装 CodeQL CLI | 无需额外安装 |

### 访问 Code Scanning 结果

**本地开发**: 访问 https://github.com/FelixWayne0318/AItrader/security/code-scanning

**CI/CD 自动化**: 由于 GitHub Actions 的 `GITHUB_TOKEN` 对 Code Scanning Alerts API 有访问限制，推荐使用 SARIF Artifact 解析。详细配置方法和故障排除参见:
- 📖 **[GitHub Actions 和 CI/CD 开发指南](docs/development/GITHUB_ACTIONS_GUIDE.md)**
  - Code Scanning Alerts 访问方法 (SARIF / PAT / Web UI)
  - 自定义 CodeQL 查询编写
  - 权限配置和 Secrets 管理
  - 常见错误故障排除

## ⚠️ 关键信息

| 项目 | 值 |
|------|-----|
| **入口文件** | `main_live.py` (不是 main.py!) |
| **服务器 IP** | 139.180.157.152 |
| **用户名** | linuxuser |
| **安装路径** | /home/linuxuser/nautilus_AItrader |
| **服务名** | nautilus-trader |
| **分支** | main |
| **Python** | 3.11+ (必须) |
| **NautilusTrader** | 1.221.0 |
| **配置文件** | ~/.env.aitrader (永久存储) |

## 配置文件管理

```
~/.env.aitrader          # 永久存储 (重装不删除)
     ↑
     │ 软链接
     │
.env ─┘                  # 项目目录中的软链接
```

| 位置 | 说明 |
|------|------|
| `~/.env.aitrader` | 永久存储，重装时自动保留 |
| `.env` | 软链接，指向 ~/.env.aitrader |

```bash
# 编辑配置
nano ~/.env.aitrader

# 查看软链接
ls -la /home/linuxuser/nautilus_AItrader/.env
```

## 部署/升级命令

```bash
# 一键清空重装 (完全重新安装)
curl -fsSL https://raw.githubusercontent.com/FelixWayne0318/AItrader/main/reinstall.sh | bash

# 或者本地执行
cd /home/linuxuser/nautilus_AItrader
chmod +x reinstall.sh && ./reinstall.sh

# 普通升级 (保留现有配置)
cd /home/linuxuser/nautilus_AItrader
git pull origin main
chmod +x setup.sh && ./setup.sh

# 安装/更新 systemd 服务
sudo cp nautilus-trader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nautilus-trader
sudo systemctl restart nautilus-trader

# 查看日志
sudo journalctl -u nautilus-trader -f --no-hostname
```

### reinstall.sh 自动修复功能 (v2.1+)

`reinstall.sh` 脚本现在包含自动诊断和修复功能，会在安装时检测并修复已知问题：

**预检查** (Step 0):
- ✅ Python 版本检查 (必须 3.11+)
- ✅ 磁盘空间检查 (建议至少 5GB)
- ✅ 内存检查 (建议至少 2GB)

**配置验证和自动修复**:
- ✅ 检查 `production.yaml` 是否包含 `network` 配置段
- ✅ 自动添加缺少的配置段
- ✅ 验证 `max_retries` 值是否足够 (至少 180 秒)
- ✅ 自动更新过低的超时配置

**安装后验证**:
- ✅ 等待服务启动 (5 秒)
- ✅ 运行健康检查脚本 (如果存在)
- ✅ 检查服务日志中的致命错误
- ✅ 报告服务状态和潜在问题

**已知问题自动修复**:
| 问题 | 自动修复 |
|------|---------|
| production.yaml 缺少 network 配置段 | ✅ 自动添加 |
| max_retries 值过低 (< 180) | ✅ 自动更新到 180 |
| Python 版本过低 | ⚠️ 警告 (需要手动升级) |
| 磁盘/内存不足 | ⚠️ 警告 (需要手动处理) |

## 常用命令

```bash
# 全面诊断 (唯一需要的检测工具)
python3 scripts/diagnose.py              # 运行全部检查
python3 scripts/diagnose.py --quick      # 快速检查 (跳过网络测试)
python3 scripts/diagnose.py --update     # 先更新代码再检查
python3 scripts/diagnose.py --restart    # 检查后重启服务
python3 scripts/diagnose.py --json       # 输出JSON格式

# 智能回归检测 (代码修改后必须运行) ⭐ 推荐
python3 scripts/smart_commit_analyzer.py           # 完整分析 (规则自动从 git 生成)
python3 scripts/smart_commit_analyzer.py --update  # 只更新规则库
python3 scripts/smart_commit_analyzer.py --validate # 只验证规则
python3 scripts/smart_commit_analyzer.py --show-rules # 查看所有规则
python3 scripts/smart_commit_analyzer.py --json    # JSON 输出 (用于 CI/CD)

# AI 深度分析 (可选，需要 DEEPSEEK_API_KEY)
python3 scripts/analyze_commits_ai.py --commits 10 # 分析最近 10 个提交

# Git 历史分析
python3 scripts/analyze_git_changes.py             # 分析最近 50 个提交
python3 scripts/analyze_git_changes.py --fix-only  # 只显示修复提交
python3 scripts/analyze_git_changes.py --commits 100 # 分析更多提交

# 服务器操作
sudo systemctl restart nautilus-trader
sudo journalctl -u nautilus-trader -f --no-hostname

# 一键更新 + 重启
python3 scripts/diagnose.py --update --restart
```

### 服务器代码同步与实时诊断

完整流程 (强制同步远程代码 + 清除缓存 + 验证版本 + 运行诊断):

```bash
# 1. 进入项目目录
cd /home/linuxuser/nautilus_AItrader

# 2. 停止服务 (避免文件锁定)
sudo systemctl stop nautilus-trader

# 3. 强制同步远程代码 + 清除缓存
git fetch origin main
git reset --hard origin/main
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# 4. 显示最近提交记录 (验证版本)
echo ""
echo "========== 最近 5 次提交 =========="
git log --oneline -5
echo ""
echo "========== 当前 HEAD =========="
git rev-parse HEAD
echo ""

# 5. 激活虚拟环境
source venv/bin/activate

# 6. 运行实时诊断
python3 scripts/diagnose_realtime.py

# 7. (可选) 重启服务
# sudo systemctl start nautilus-trader
```

**一行命令版本** (复制粘贴即用):

```bash
cd /home/linuxuser/nautilus_AItrader && sudo systemctl stop nautilus-trader && git fetch origin main && git reset --hard origin/main && find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null && echo "=== 最近提交 ===" && git log --oneline -5 && source venv/bin/activate && python3 scripts/diagnose_realtime.py
```

| 步骤 | 命令 | 作用 |
|------|------|------|
| 停止服务 | `systemctl stop` | 避免运行中的进程锁定文件 |
| 强制同步 | `git reset --hard origin/main` | 丢弃本地修改，完全同步远程 |
| 清除缓存 | `find ... __pycache__` | 删除 Python 编译缓存，确保使用最新代码 |
| 显示提交 | `git log --oneline -5` | 核对 commit hash 确认版本 |
| 实时诊断 | `scripts/diagnose_realtime.py` | 调用真实 API，验证完整数据流 |

### 实时诊断工具 (diagnose_realtime.py)

```bash
cd /home/linuxuser/nautilus_AItrader
source venv/bin/activate

# 完整诊断 (详细输出)
python3 scripts/diagnose_realtime.py

# 仅显示关键结果 (跳过详细分析)
python3 scripts/diagnose_realtime.py --summary

# 导出到本地文件
python3 scripts/diagnose_realtime.py --export

# 导出并推送到 GitHub (远程查看)
python3 scripts/diagnose_realtime.py --export --push
```

| 参数 | 说明 |
|------|------|
| (无参数) | 完整诊断，详细输出所有数据 |
| `--summary` | 仅显示关键结果，跳过中间分析 |
| `--export` | 保存到 `logs/diagnosis_YYYYMMDD_HHMMSS.txt` |
| `--push` | 配合 `--export` 推送到 GitHub 仓库 |

**GitHub 推送前提条件**：
- 服务器已配置 SSH Key 用于 GitHub 推送
- 远程仓库 URL 已设置为 SSH 格式: `git@github.com:FelixWayne0318/AItrader.git`

**配置 SSH Key (如需)**：
```bash
# 1. 生成 SSH Key (如果没有)
ssh-keygen -t ed25519 -C "your_email@example.com"

# 2. 复制公钥到 GitHub Settings > SSH Keys
cat ~/.ssh/id_ed25519.pub

# 3. 修改远程 URL 为 SSH 格式
git remote set-url origin git@github.com:FelixWayne0318/AItrader.git

# 4. 测试连接
ssh -T git@github.com
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

4. **非 ASCII 符号崩溃** (币安人生USDT-PERP) - **彻底修复**
   - 问题：Binance API 返回非 ASCII 符号导致 Rust 代码 panic
   - 错误：`Condition failed: invalid string for 'value' contained a non-ASCII char`
   - 根因：NautilusTrader 旧版本 Rust 代码只接受 ASCII
   - **最终修复**：升级到 Python 3.11 + NautilusTrader 1.221.0
   - 官方修复：[GitHub Issue #3053](https://github.com/nautechsystems/nautilus_trader/issues/3053), [PR #3105](https://github.com/nautechsystems/nautilus_trader/pull/3105)
   - 注意：1.211.0 只修复了 Currency，1.221.0 才完整修复 Symbol/PositionId

5. **LoggingConfig 兼容性** (NautilusTrader 1.202.0)
   - 问题：`log_file_format` 和 `log_colors` 参数不被支持
   - 修复：移除这两个参数

6. **多代理分歧处理** (skip_on_divergence) → **已被 TradingAgents 架构取代**
   - 问题：当 DeepSeek 和 MultiAgent 信号完全对立 (BUY vs SELL) 时，信号合并会导致过多 HOLD
   - **TradingAgents 修复**：改用层级决策架构，MultiAgent Judge 作为唯一决策者
   - 架构：Bull/Bear 辩论 (2 AI calls) → Judge 决策 (1 AI call, optimized prompt) → Risk 评估 (1 AI call) → 最终信号
   - 优化：Judge 使用量化决策框架，减少主观判断，降低 HOLD 比例
   - 参考：[TradingAgents Framework](https://github.com/TauricResearch/TradingAgents) UCLA/MIT 论文
   - 文件：`strategy/deepseek_strategy.py`, `agents/multi_agent_analyzer.py`
   - 注意：`skip_on_divergence` 和 `use_confidence_fusion` 配置项已标记为 LEGACY，不再生效

7. **时间周期解析Bug**
   - 问题：`15-MINUTE` 被错误解析为 `5m`
   - 原因：`5-MINUTE` 是 `15-MINUTE` 的子字符串
   - 修复：调整检查顺序，先检查更长的字符串
   - 影响文件：`strategy/deepseek_strategy.py`, `scripts/diagnose_realtime.py`

8. **Rust RSI 线程安全崩溃** (Telegram 命令处理)
   - 问题：服务崩溃，Rust panic: `RelativeStrengthIndex is unsendable, but sent to another thread`
   - 原因：Telegram 命令处理在后台线程 (Thread 7) 运行，访问了 `indicator_manager`
   - 根因：NautilusTrader 的 Rust 指标 (RSI, MACD) 不是 Send/Sync，不能跨线程访问
   - 修复：添加 `_cached_current_price` 变量，在 `on_bar` 中线程安全更新
   - 影响方法：`_cmd_status()`, `_cmd_position()` 改用缓存价格
   - 文件：`strategy/deepseek_strategy.py`

9. **Telegram Webhook 冲突** (polling 模式失败)
   - 问题：服务启动后持续报错 `can't use getUpdates method while webhook is active`
   - 原因：Bot 之前被设置了 webhook，与 polling 模式冲突
   - 根因：`delete_webhook()` 调用时机太晚，在 `Application.initialize()` 之后
   - 修复：添加 `_delete_webhook_standalone()` 方法，在初始化前先删除 webhook
   - 改进：双重删除 (初始化前 + 初始化后)，冲突重试时也删除
   - 文件：`utils/telegram_command_handler.py`
   - 手动修复：`curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"`

10. **循环导入错误** (agents ↔ strategy)
    - 问题：启动时报错 `ImportError: cannot import name 'MultiAgentAnalyzer' from partially initialized module`
    - 原因：`agents/__init__.py` 导入 `multi_agent_analyzer` → 导入 `trading_logic` → 导入 `strategy` → 循环
    - 根因：`__init__.py` 中的自动导入触发了循环依赖链
    - 修复：移除 `agents/__init__.py` 和 `strategy/__init__.py` 中的自动导入
    - 使用方式：直接导入 `from agents.multi_agent_analyzer import MultiAgentAnalyzer`
    - 文件：`agents/__init__.py`, `strategy/__init__.py`

11. **DeepSeek net_sentiment KeyError** (情绪数据缺失)
    - 问题：AI 分析失败，报错 `KeyError: 'net_sentiment'`
    - 原因：当真实情绪数据不可用时，默认情绪结构缺少必需字段
    - 根因：默认情绪数据没有 `net_sentiment`, `positive_ratio`, `negative_ratio`
    - 修复：在默认情绪数据中添加所有必需字段
    - 防护：`_format_sentiment_data()` 改用 `.get()` 防止 KeyError
    - 文件：`strategy/deepseek_strategy.py`, `utils/deepseek_client.py`

12. **Telegram TCPTransport closed 错误** (跨事件循环问题)
    - 问题：发送 Telegram 消息时报错 `RuntimeError: unable to perform operation on <TCPTransport closed=True>`
    - 原因：python-telegram-bot v20+ 是完全异步的，不是线程安全的
    - 根因：混合 asyncio 和 threading 会导致 httpx 会话冲突
    - 修复：`send_message_sync` 改用 `requests` 直接调用 Telegram Bot API (官方推荐)
    - 参考：[PTB Discussion #4096](https://github.com/python-telegram-bot/python-telegram-bot/discussions/4096)
    - 文件：`utils/telegram_bot.py`

13. **Rust 指标线程安全 panic** (on_timer 崩溃)
    - 问题：服务崩溃，Rust panic: `RelativeStrengthIndex is unsendable, but sent to another thread`
    - 原因：使用 `nautilus_trader.core.nautilus_pyo3` 的 Rust 指标
    - 根因：Rust 指标有严格的 Send/Sync 检查，on_timer 在不同线程运行
    - 修复：改用 `nautilus_trader.indicators` 的 Cython 指标（与原始仓库一致）
    - 参考：[原始仓库](https://github.com/Patrick-code-Bot/nautilus_AItrader)
    - 文件：`indicators/technical_manager.py`
    - 注意：**不要**从 `nautilus_trader.core.nautilus_pyo3` 导入指标

14. **仪器加载超时问题** (服务启动后立即退出)
    - 问题：服务启动后立即退出，日志显示 "Trading session ended"，exit code 0
    - 根因：`load_all=True` 加载所有 Binance 合约需要 1-3 分钟，但 `max_retries: 60` 只给了 60 秒
    - 症状：无错误消息，服务在 `on_start()` 等待仪器超时后调用 `self.stop()` 正常退出
    - 修复：增加 `configs/production.yaml` 中的 `network.instrument_discovery.max_retries: 180`
    - 文件：`configs/production.yaml`, `configs/base.yaml`
    - 相关代码：`main_live.py:343-356` (InstrumentProviderConfig)
    - 替代方案：改用 `load_ids=[instrument_id]` 只加载需要的仪器（启动更快，< 5 秒）

15. **YAML 配置文件语法错误** (production.yaml 缺少 network 配置段)
    - 问题：配置加载失败，报错 `expected '<document start>', but found '<scalar>'`
    - 根因：`configs/production.yaml` 缺少 `network` 配置段
    - 修复：添加完整的 `network.instrument_discovery` 配置段
    - 文件：`configs/production.yaml`

16. **健康检查脚本 bug** (health_check.sh v2.1-v2.3)
    - **问题 1**: Bash 语法错误 (`[: 0\n0: integer expression expected`)
      - 根因：`grep -ci` 返回值包含换行符，导致变量值为 `"0\n0"` 而非 `"0"`
      - 修复：添加 `tr -d '\n'` 清除换行符
    - **问题 2**: 服务运行时长计算错误 (显示 29480588 分钟)
      - 根因：`date +%s%N` 与 `ActiveEnterTimestampMonotonic` 时间基准不同
      - 修复：改用 `/proc/uptime` 计算 (与 monotonic clock 同步)
    - **问题 3**: 仪器超时检测错误 (显示 2 秒而非 180 秒)
      - 根因：`base.yaml` 中有多个 `max_retries` 字段，`grep` 提取到错误的值
      - 修复：使用 Python YAML 解析器正确提取嵌套路径 `network.instrument_discovery.max_retries`
      - 配置优先级：先检查 `production.yaml`，回退到 `base.yaml`
    - 文件：`scripts/health_check.sh`

## 常见错误避免

- ❌ 使用 `python` 命令 → ✅ **始终使用 `python3`** (确保使用正确版本)
- ❌ 使用 `main.py` 作为入口 → ✅ 使用 `main_live.py`
- ❌ 忘记设置 `AUTO_CONFIRM=true` → 会卡在确认提示
- ❌ 止损在入场价错误一侧 → 已修复，会自动回退到默认2%
- ❌ 使用 Python 3.10 → ✅ 必须使用 Python 3.11+
- ❌ 从后台线程访问 `indicator_manager` → ✅ 使用 `_cached_current_price` (Rust 指标不可跨线程)
- ❌ 使用 `nautilus_trader.core.nautilus_pyo3` 的指标 → ✅ 使用 `nautilus_trader.indicators` (Cython 版本，线程安全)
- ❌ 在 `__init__.py` 中自动导入 → ✅ 直接导入模块 (避免循环导入)
- ❌ 直接访问 `sentiment_data['key']` → ✅ 使用 `sentiment_data.get('key', default)` (防止 KeyError)
- ❌ **在环境变量中存放业务参数** → ✅ **业务参数只在 configs/*.yaml 中** (环境变量仅用于 API keys)
- ❌ **服务器命令不带 cd** → ✅ **始终先 cd 到项目目录**
  ```bash
  # 错误：直接执行命令会报 "not a git repository"
  git status

  # 正确：始终以 cd 开头
  cd /home/linuxuser/nautilus_AItrader && git status
  ```
- ❌ **仪器加载超时配置不足** → ✅ **production.yaml 中设置 max_retries: 180** (`load_all=true` 需要 1-3 分钟)
- ❌ **YAML 配置文件缺少必需配置段** → ✅ **确保 production.yaml 包含 network 配置段**
- ❌ **使用 bash grep/awk 解析 YAML** → ✅ **使用 Python yaml.safe_load() 解析嵌套配置**

## 文件结构

```
/home/user/AItrader/
├── main_live.py              # 入口文件 (不是 main.py!)
├── setup.sh                  # 一键部署脚本 (普通升级)
├── reinstall.sh              # 一键清空重装脚本 (完全重新安装)
├── requirements.txt          # Python 依赖
├── nautilus-trader.service   # systemd 服务文件
│
├── .github/                  # GitHub 配置
│   ├── workflows/            # GitHub Actions
│   │   ├── commit-analysis.yml   # 智能提交分析 (每次 push/PR 自动运行)
│   │   ├── codeql-analysis.yml   # CodeQL 安全分析 (每周 + push 到 main)
│   │   └── claude.yml            # Claude Code Action
│   └── codeql/               # CodeQL 自定义查询
│       └── custom-queries/   # 项目专用查询
│           ├── qlpack.yml        # 查询包配置
│           ├── find-imports.ql   # 追踪所有 import
│           └── hardcoded-paths.ql # 检测硬编码路径
│
├── .claude/                  # Claude Code 配置
│   ├── settings.json         # 权限配置
│   └── skills/               # 自定义技能
│
├── strategy/                 # 策略模块
│   ├── deepseek_strategy.py  # 主策略 (含止损修复)
│   └── trading_logic.py      # 交易逻辑常量和函数
│
├── agents/                   # 多代理系统
│   └── multi_agent_analyzer.py # 多代理分析 (Bull/Bear/Judge)
│
├── indicators/               # 技术指标
│   └── technical_manager.py  # 技术指标管理器 (Cython 版本)
│
├── utils/                    # 工具模块
│   ├── config_manager.py     # 统一配置管理器 (ConfigManager)
│   ├── deepseek_client.py    # DeepSeek AI 客户端
│   ├── sentiment_client.py   # Binance 多空比
│   ├── telegram_bot.py       # Telegram 通知
│   ├── telegram_command_handler.py # Telegram 命令处理
│   ├── binance_account.py    # Binance 账户工具
│   ├── bar_persistence.py    # K线数据持久化
│   └── oco_manager.py        # OCO 订单管理
│
├── patches/                  # 兼容性补丁
│   ├── binance_enums.py      # Binance 枚举兼容性补丁
│   └── binance_positions.py  # Binance 持仓处理补丁
│
├── configs/                  # 配置文件 (分层架构)
│   ├── base.yaml             # 基础配置 (所有参数定义)
│   ├── production.yaml       # 生产环境覆盖
│   ├── development.yaml      # 开发环境覆盖
│   ├── backtest.yaml         # 回测环境覆盖
│   ├── auto_generated_rules.json # 自动生成的回归规则
│   ├── strategy_config.yaml  # 旧版策略配置 (兼容)
│   └── telegram_config.yaml  # Telegram 配置
│
├── scripts/                  # 脚本工具
│   ├── # === 诊断工具 ===
│   ├── diagnose.py           # 全面诊断工具 v2.0
│   ├── diagnose_realtime.py  # 实时 API 诊断
│   ├── diagnose_telegram.py  # Telegram 诊断
│   ├── diagnose_no_signal.py # 无信号诊断
│   ├── comprehensive_diagnosis.py # 全面诊断
│   │
│   ├── # === 提交分析工具 (GitHub Actions 自动运行) ===
│   ├── smart_commit_analyzer.py  # 智能回归检测 (规则自动从 git 生成)
│   ├── analyze_commits_ai.py     # AI 深度语义分析 (DeepSeek)
│   ├── analyze_dependencies.py   # Python AST 依赖分析 (循环依赖检测)
│   ├── analyze_git_changes.py    # Git 历史分析
│   ├── validate_commit_fixes.py  # 旧版手动规则检查
│   │
│   ├── # === 配置工具 ===
│   ├── validate_path_aliases.py  # 配置路径验证
│   ├── benchmark_config.py       # 配置性能测试
│   ├── check_circular_imports.sh # 循环导入检测
│   │
│   ├── # === 部署工具 ===
│   ├── full_deploy.sh        # 完整部署
│   ├── server_redeploy.sh    # 服务器重部署
│   ├── sync_from_repo.sh     # 代码同步
│   ├── health_check.sh       # 健康检查
│   └── install-hooks.sh      # Git hooks 安装
│
├── tests/                    # 测试目录
│   ├── test_bracket_order.py
│   ├── test_integration_mock.py
│   ├── test_rounding_fix.py
│   ├── test_strategy_components.py
│   ├── test_binance_patch.py
│   ├── test_multi_agent.py
│   ├── test_telegram.py
│   └── test_telegram_commands.py
│
├── tools/                    # 运维工具
│   ├── debug_binance_positions.py  # Binance 持仓调试
│   ├── debug_telegram_config.py    # Telegram 配置调试
│   ├── monitor_redis.py            # Redis 监控
│   ├── monitor_emulated_orders.sh  # OCO 订单监控
│   └── check_emulated_status.sh    # OCO 状态检查
│
├── docs/                     # 文档目录
│   ├── DEPLOYMENT.md         # 部署指南
│   ├── SECURITY.md           # 安全指南
│   ├── REFERENCE.md          # 参考文档
│   ├── SYSTEM_OVERVIEW.md    # 系统概述
│   ├── architecture/         # 架构文档
│   ├── features/             # 功能文档
│   ├── strategy/             # 策略文档
│   ├── setup/                # 安装文档
│   ├── troubleshooting/      # 故障排除
│   ├── releases/             # 发布说明
│   └── development/          # 开发文档
│
├── web/                      # Web 管理界面 (可选)
│   ├── backend/              # FastAPI 后端
│   └── frontend/             # 前端 (Vue/React)
│
├── CLAUDE.md                 # 本文档 (AI 助手指南)
├── README.md                 # 项目文档
└── QUICKSTART.md             # 快速入门
```

## 🎨 Web 前端设计规范 (DipSway 风格)

### 导航栏设计原则

导航栏采用 **DipSway 风格**：透明背景 + 独立浮动组件组。

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ❌ 错误: 整个导航栏有统一的黑色/深色背景                                  │
│  ✅ 正确: 导航栏本身透明，每个组件组有独立的半透明圆角背景                 │
└──────────────────────────────────────────────────────────────────────────┘
```

### 组件组结构

| 组件组 | 背景 | 说明 |
|--------|------|------|
| Logo (AlgVex) | 无背景 | 只显示 Logo 图标 + 文字 |
| 导航 (Home/Chart/Performance/Copy Trading) | `bg-background/60 backdrop-blur-xl border rounded-xl` | 独立浮动圆角背景 |
| Bot Status | `bg-background/60 backdrop-blur-xl border rounded-xl` | 独立浮动圆角背景 |
| Signal | `bg-background/60` 或信号颜色 | 独立浮动圆角背景 |
| Markets 下拉菜单 | `bg-background/60 backdrop-blur-xl border rounded-xl` | 独立浮动圆角背景 |
| 语言选择 | `bg-background/60 backdrop-blur-xl border rounded-xl` | 独立浮动圆角背景 |
| CTA 按钮 | `bg-gradient-to-r from-primary to-primary/80` | 主色渐变 |

### 间距规则

```
[Logo] ----ml-8---- [Nav Group] ----flex-1---- [Bot|Signal|Markets] --ml-3-- [Lang|CTA]
                                                    ↑
                                            gap-1.5 (较小间距)
```

- **导航组与后续组件**: `ml-8` (较大间距)
- **Bot/Signal/Markets 之间**: `gap-1.5` (较小间距)
- **语言/CTA 与前面组件**: `ml-3`

### 响应式设计

| 屏幕类型 | 显示内容 |
|----------|----------|
| **桌面 (lg+)** | 全部组件 |
| **手机横屏 (landscape)** | 同桌面 |
| **手机竖屏 (portrait)** | Logo + Bot Status + Signal + 汉堡菜单 |

**Tailwind 断点配置** (`tailwind.config.ts`):

```typescript
screens: {
  'landscape': { 'raw': '(orientation: landscape) and (max-height: 500px)' },
}
```

### 手机竖屏菜单内容

点击汉堡菜单展开:
- 导航链接 (Home/Chart/Performance/Copy Trading)
- Market Data (4 个指标: Long/Short, Funding Rate, OI, Volume)
- 语言切换 + CTA 按钮

### CTA 按钮设计

两个主要 CTA 按钮样式一致：

```tsx
// Start Copy Trading - 主按钮
className="bg-gradient-to-r from-primary to-primary/80 shadow-lg shadow-primary/25 border border-primary/20"

// Live Chart - 次要按钮
className="bg-background/60 backdrop-blur-xl border border-border/50 hover:border-primary/30"
```

### 前端部署流程

**关键**: 每次部署必须清除 `.next` 缓存，否则 Tailwind CSS 响应式类可能失效。

```bash
cd /home/linuxuser/nautilus_AItrader/web/frontend
rm -rf .next                 # 关键! 清除缓存
npm run build                # 重新构建
pm2 restart algvex-frontend  # 重启服务
```

**参考**:
- [Tailwind CSS Production Issues](https://github.com/tailwindlabs/tailwindcss/discussions/8521)
- 部署脚本: `web/frontend/scripts/deploy.sh`

## 配置管理

**重要更新 (Phase 1-2 完成)**: 配置现通过 ConfigManager 统一管理，支持多环境切换。

### ConfigManager 使用

```python
from utils.config_manager import ConfigManager

# 加载生产环境配置
config = ConfigManager(env='production')
config.load()

# 访问配置值
temperature = config.get('ai', 'deepseek', 'temperature')
equity = config.get('capital', 'equity')
```

### 命令行环境切换

```bash
# 生产环境 (15分钟K线, INFO日志)
python3 main_live.py --env production

# 开发环境 (1分钟K线, DEBUG日志)
python3 main_live.py --env development

# 回测环境 (固定资金, 无Telegram)
python3 main_live.py --env backtest

# 验证配置 (加载但不启动交易)
python3 main_live.py --env development --dry-run
```

### 配置文件结构

配置采用分层加载机制：
- **base.yaml** - 完整配置定义 (所有参数)
- **production.yaml** - 生产环境覆盖
- **development.yaml** - 开发环境覆盖
- **backtest.yaml** - 回测环境覆盖
- **~/.env.aitrader** - 敏感信息 (API keys)

### 配置验证工具

```bash
# 验证配置路径别名
python3 scripts/validate_path_aliases.py

# 性能基线测试 (目标 < 200ms)
python3 scripts/benchmark_config.py

# 循环导入检测
bash scripts/check_circular_imports.sh
```

## 配置参数完整列表

配置分为两部分：
- **敏感信息**: `~/.env.aitrader` (API 密钥等)
- **策略参数**: `configs/base.yaml` (通过环境文件覆盖)

### 环境变量 (~/.env.aitrader)

**⚠️ 重要：环境变量仅用于敏感信息，禁止存放业务参数！**

```bash
# ===== 允许的内容 (仅敏感信息) =====
BINANCE_API_KEY=xxx           # Binance API Key
BINANCE_API_SECRET=xxx        # Binance API Secret
DEEPSEEK_API_KEY=xxx          # DeepSeek AI API Key
TELEGRAM_BOT_TOKEN=xxx        # Telegram Bot Token
TELEGRAM_CHAT_ID=xxx          # 你的个人用户 ID

# ===== 禁止的内容 (业务参数应在 configs/*.yaml 中) =====
# ❌ EQUITY=1000              # 应在 configs/base.yaml: capital.equity
# ❌ LEVERAGE=5               # 应在 configs/base.yaml: capital.leverage
# ❌ BASE_POSITION_USDT=100   # 应在 configs/base.yaml: position.base_usdt_amount
# ❌ TIMER_INTERVAL_SEC=900   # 应在 configs/production.yaml: timing.timer_interval_sec
# ❌ LOG_LEVEL=INFO           # 应在 configs/production.yaml: logging.level
```

**为什么业务参数不应该在环境变量中？**
1. 环境变量是扁平结构，无法表达复杂配置
2. 难以追踪配置来源 (YAML 有版本控制)
3. 容易造成配置分散，维护困难
4. 参考：[12-Factor Config Misunderstandings](https://blog.doismellburning.co.uk/twelve-factor-config-misunderstandings-and-advice/)

### 策略参数 (configs/base.yaml)

**注意**: 旧版 `strategy_config.yaml` 已被新的分层配置取代，但仍保留用于兼容。
新系统使用 `base.yaml` + 环境覆盖文件 (`production.yaml`, `development.yaml`, `backtest.yaml`)。

#### 资金配置
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `equity` | 1000 | 备用资金值 (自动获取真实余额时不用) |
| `leverage` | 5 | 杠杆倍数 (建议 3-10) |
| `use_real_balance_as_equity` | true | 自动从 Binance 获取真实余额 |

#### 仓位管理
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `base_usdt_amount` | 100 | 基础仓位 USDT (Binance 最低 $100) |
| `high_confidence_multiplier` | 1.5 | 高信心仓位乘数 → $150 |
| `medium_confidence_multiplier` | 1.0 | 中等信心 → $100 |
| `low_confidence_multiplier` | 0.5 | 低信心 → $50 |
| `max_position_ratio` | 0.30 | 最大仓位比例 (30% of equity) |

#### 风险管理
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_confidence_to_trade` | MEDIUM | 最低交易信心 (LOW/MEDIUM/HIGH) |
| `skip_on_divergence` | true | AI 分歧时跳过交易 (保守模式后备) |
| `use_confidence_fusion` | true | 启用加权信心融合 (推荐) |
| `rsi_extreme_threshold_upper` | 70 | RSI 超买阈值 |
| `rsi_extreme_threshold_lower` | 30 | RSI 超卖阈值 |

**加权信心融合说明**：当 DeepSeek 和 MultiAgent 信号相反时 (BUY vs SELL)，使用信心更高的信号：
- HIGH 权重=3, MEDIUM=2, LOW=1
- 例：DeepSeek=BUY(HIGH) vs MultiAgent=SELL(MEDIUM) → 使用 BUY
- 只有权重相等时才跳过交易

#### 止损止盈
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_auto_sl_tp` | true | 启用自动止损止盈 |
| `sl_buffer_pct` | 0.001 | 止损缓冲 (0.1%) |
| `tp_high_confidence_pct` | 0.03 | 高信心止盈 3% |
| `tp_medium_confidence_pct` | 0.02 | 中等信心止盈 2% |
| `tp_low_confidence_pct` | 0.01 | 低信心止盈 1% |

#### 移动止损
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_trailing_stop` | true | 启用移动止损 |
| `trailing_activation_pct` | 0.01 | 盈利 1% 后启动 |
| `trailing_distance_pct` | 0.005 | 跟踪距离 0.5% |

#### AI 配置
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `deepseek.model` | deepseek-chat | DeepSeek 模型 |
| `deepseek.temperature` | 0.3 | 温度参数 |
| `debate_rounds` | 2 | 多代理辩论轮数 (1-3) |

#### 定时器
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `timer_interval_sec` | 900 | 分析间隔 (秒)，15分钟 |

#### 多时间框架 (MTF) 配置 v3.6 🆕

**功能状态**: ✅ **已启用** (`multi_timeframe.enabled: true`)

MTF (Multi-Timeframe) 框架使用三层时间周期协同决策，结合订单流和衍生品数据增强 AI 分析质量。

##### v3.6 新增数据 (完整数据覆盖)

| 数据字段 | 说明 | 来源 |
|---------|------|------|
| `period_high` | K线周期内最高价 | indicator_manager.recent_bars |
| `period_low` | K线周期内最低价 | indicator_manager.recent_bars |
| `period_change_pct` | K线周期内价格变化百分比 | 计算: (当前价-开盘价)/开盘价 |
| `period_hours` | K线周期覆盖的小时数 | 计算: bars数量 * 15分钟 / 60 |
| `volume_usdt` | 24小时成交额 (USDT) | Binance K线数据 |
| `price_change` | 24小时价格变化百分比 | Binance ticker API |

##### 架构设计

基于 [TradingAgents](https://github.com/TauricResearch/TradingAgents) (UCLA/MIT) 框架的三层决策架构：

```
┌─────────────────────────────────────────────────────────────┐
│  趋势层 (1D) - Risk-On/Risk-Off Filter                      │
│  ├─ SMA_200: 长期趋势判断                                   │
│  ├─ MACD: 趋势强度确认                                      │
│  └─ 作用: 熊市阻止所有交易，牛市放行                        │
└─────────────────────────────────────────────────────────────┘
                          ↓ (RISK_ON)
┌─────────────────────────────────────────────────────────────┐
│  决策层 (4H) - Bull/Bear Debate + Judge Decision            │
│  ├─ 数据源: 技术指标 + 订单流 + 衍生品 + 情绪               │
│  ├─ Bull Analyst: 多头论据 (temperature=0.3)                │
│  ├─ Bear Analyst: 空头论据 (temperature=0.3)                │
│  ├─ Judge: 量化决策框架 (确认计数, temperature=0.1)         │
│  └─ 作用: 确定交易方向 (LONG/SHORT/HOLD)                    │
└─────────────────────────────────────────────────────────────┘
                          ↓ (LONG/SHORT)
┌─────────────────────────────────────────────────────────────┐
│  执行层 (15M) - Precise Entry Timing                         │
│  ├─ RSI: 入场时机 (避免超买超卖)                            │
│  ├─ Support/Resistance: 止损止盈价位                        │
│  └─ 作用: 精确入场 + 风险管理                               │
└─────────────────────────────────────────────────────────────┘
```

##### 核心功能

| 功能模块 | 说明 | 配置参数 |
|---------|------|----------|
| **趋势过滤** | 1D 周期判断宏观趋势，熊市阻止交易 | `trend_layer.*` |
| **订单流分析** | Buy/Sell Ratio, CVD, 大单检测 | `order_flow.*` |
| **衍生品数据** | OI (持仓量), Funding Rate, Liquidations | `coinalyze.*` |
| **多层协同** | 三层过滤 + 降级策略 | `decision_layer.*`, `execution_layer.*` |
| **数据增强** | AI 看到 4 类数据 (原 2 类) | `order_flow.enabled`, `coinalyze.enabled` |

##### 订单流数据 (Order Flow)

| 指标 | 数据源 | 说明 |
|------|--------|------|
| **Buy/Sell Ratio** | Binance K线 [taker_buy_volume] | 买盘/卖盘力量对比，>0.55 多头主导 |
| **CVD Trend** | Cumulative Volume Delta | 累积成交量差，判断资金流向 (RISING/FALLING) |
| **Avg Trade Size** | quote_volume / trades_count | 平均成交额，识别机构大单 |
| **Recent 10 Bars** | 滑动窗口 | 短期趋势确认 |

##### 衍生品数据 (Derivatives)

| 指标 | 数据源 | 说明 |
|------|--------|------|
| **Open Interest** | Coinalyze API | 持仓量变化，确认趋势强度 (+5% = 强趋势) |
| **Funding Rate** | Coinalyze API | 资金费率，判断多空情绪 (>0.01% 多头过热) |
| **Liquidations (1h)** | Coinalyze API | 爆仓数据，极端行情信号 (单位: BTC，需乘价格转 USD) |

**注意**: Coinalyze 数据需要 API Key，失败时自动降级到中性值。

##### 配置示例

```yaml
# configs/base.yaml:290-395
multi_timeframe:
  enabled: true                      # 启用 MTF

  trend_layer:                       # 趋势层 (1D)
    timeframe: "1d"
    sma_period: 200
    require_above_sma: true          # 价格需在 SMA_200 上方

  decision_layer:                    # 决策层 (4H)
    timeframe: "4h"
    debate_rounds: 2                 # Bull/Bear 辩论轮数

  execution_layer:                   # 执行层 (15M)
    default_timeframe: "15m"
    rsi_entry_min: 35                # RSI 入场范围
    rsi_entry_max: 65

order_flow:
  enabled: true                      # 启用订单流
  binance:
    bars_for_analysis: 10            # 分析最近 10 根 K线
  buy_ratio:
    bullish_threshold: 0.55          # >55% 视为多头

coinalyze:
  enabled: true                      # 启用衍生品数据
  api_key: ""                        # 从 ~/.env.aitrader 读取 COINALYZE_API_KEY
  fallback_enabled: true             # API 失败时使用默认值
```

##### 环境变量 (可选)

```bash
# ~/.env.aitrader
COINALYZE_API_KEY=your_api_key_here  # 获取: https://coinalyze.net/
```

如果没有 API Key，系统会自动降级，仍可正常运行（使用 Binance 订单流数据）。

##### 数据流程

```
1. on_timer (15分钟触发)
   ↓
2. AIDataAssembler 聚合数据
   ├─ BinanceKlineClient (订单流)
   ├─ CoinalyzeClient (衍生品)
   ├─ SentimentClient (多空比)
   └─ IndicatorManager (技术指标)
   ↓
3. MultiAgentAnalyzer
   ├─ Bull Analyst (看多论据)
   ├─ Bear Analyst (看空论据)
   └─ Judge (量化决策)
   ↓
4. Risk Manager (仓位大小 + SL/TP)
   ↓
5. 最终交易信号
```

##### 降级策略

| 故障场景 | 降级行为 | 影响 |
|---------|---------|------|
| Coinalyze API 失败 | 使用中性默认值 (OI=0, Funding=0) | AI 分析仅依赖订单流 + 技术指标 |
| Binance K线失败 | 使用 indicator_manager 缓存数据 | 订单流数据不可用，仅用技术指标 |
| 趋势层数据不足 | RISK_OFF (阻止交易) | 等待足够历史数据 |

##### 预期改进

- **信号质量**: 订单流确认真实交易意愿，减少假突破
- **风险控制**: 衍生品数据预警爆仓风险和资金费率挤压
- **决策效率**: Judge 确认计数算法减少主观 HOLD 偏向

##### 相关文档

- 完整实现方案: [docs/MTF_UNIMPLEMENTED_FEATURES.md](docs/MTF_UNIMPLEMENTED_FEATURES.md)
- 评估报告: [docs/MTF_EVALUATION_AND_FIXES.md](docs/MTF_EVALUATION_AND_FIXES.md)
- TradingAgents 框架: https://github.com/TauricResearch/TradingAgents

#### 订单簿深度 (Order Book Depth) 配置 v3.7 🆕

**功能状态**: ⚠️ **已实施，默认禁用** (`order_book.enabled: false`)

订单簿深度数据提供盘口流动性和不平衡指标，帮助 AI 理解市场微观结构。

##### 核心指标 (v2.0)

| 指标 | 说明 | 版本 |
|------|------|------|
| **Simple OBI** | 买卖压力对比 | v1.0 |
| **Weighted OBI** | 靠近盘口权重更高 | v1.0 |
| **Adaptive OBI** | 基于波动率动态调整衰减因子 | ⭐ v2.0 |
| **Dynamics** | 追踪 OBI/深度变化趋势 | ⭐ v2.0 Critical |
| **Pressure Gradient** | 近档/远档压力梯度 | ⭐ v2.0 |
| **Slippage (含置信度)** | 执行 N BTC 的预期滑点 + 不确定性 | ⭐ v2.0 |
| **Dynamic Anomaly** | 基于波动率自适应阈值检测大单 | ⭐ v2.0 |

##### 配置示例

```yaml
# configs/base.yaml
order_book:
  enabled: false                      # 启用订单簿数据 (Phase 2 测试后启用)

  api:
    limit: 100                        # 深度档位数
    timeout: 10
    max_retries: 2

  processing:
    weighted_obi:
      base_decay: 0.8                 # 基础衰减因子
      adaptive: true                  # 启用自适应衰减
      volatility_factor: 0.1          # 波动率影响因子

    anomaly_detection:
      base_threshold: 3.0             # 基础异常阈值 (倍数)
      dynamic: true                   # 启用动态调整

    slippage_amounts:
      - 0.1                           # 0.1 BTC
      - 0.5                           # 0.5 BTC
      - 1.0                           # 1.0 BTC

    history:
      size: 10                        # 缓存最近 N 次快照
```

##### v2.0 关键改进

| 改进项 | 说明 | 重要性 |
|--------|------|--------|
| **NO_DATA 状态** | 避免 AI 误判中性市场 | ⭐ Critical |
| **变化率指标** | dynamics 段，追踪 OBI/深度变化趋势 | ⭐ Critical |
| **自适应加权 OBI** | 基于波动率调整衰减因子 | Recommended |
| **Pressure Gradient** | 近档/远档压力梯度 | Recommended |
| **滑点不确定性** | 滑点估算加入置信度和范围 | Recommended |

##### 诊断工具

```bash
# 测试订单簿功能
python3 scripts/diagnose_orderbook.py

# 自定义参数
python3 scripts/diagnose_orderbook.py --symbol ETHUSDT --limit 50 --volatility 0.03
```

##### 相关文档

- 完整实施方案 v2.0: [docs/ORDER_BOOK_IMPLEMENTATION_PLAN.md](docs/ORDER_BOOK_IMPLEMENTATION_PLAN.md)
- 专家评估得分: **8.58/10** (强烈推荐实施)
- 参考论文: Cont et al. (2014), Cartea et al. (2015)

##### 启用流程 (Phase 2)

1. **测试**: `python3 scripts/diagnose_orderbook.py` 验证功能
2. **回测**: 在开发环境运行一段时间，观察 AI 决策质量
3. **A/B 测试**: 对比有/无订单簿数据的 Sharpe Ratio
4. **启用**: `configs/base.yaml` 中设置 `order_book.enabled: true`
5. **监控**: 观察数据质量和性能影响

### Telegram 命令

| 命令 | 说明 |
|------|------|
| `/menu` | 显示交互按钮菜单 |
| `/status` | 查看系统状态和真实余额 |
| `/position` | 查看当前持仓 |
| `/orders` | 查看挂单 |
| `/history` | 最近交易记录 |
| `/risk` | 风险指标 |
| `/pause` | 暂停交易 |
| `/resume` | 恢复交易 |
| `/close` | 平仓 |

### 修改配置

```bash
# 修改基础策略参数 (所有环境共享)
nano /home/linuxuser/nautilus_AItrader/configs/base.yaml

# 修改生产环境特定参数
nano /home/linuxuser/nautilus_AItrader/configs/production.yaml

# 修改开发环境特定参数
nano /home/linuxuser/nautilus_AItrader/configs/development.yaml

# 修改 API 密钥 (敏感信息)
nano ~/.env.aitrader

# 修改后重启服务生效
sudo systemctl restart nautilus-trader
```

## GitHub Actions 自动化

每次 push 到 main 或创建 PR 时，自动运行以下检查：

| 工作流 | 文件 | 功能 |
|--------|------|------|
| **Commit Analysis** | `.github/workflows/commit-analysis.yml` | 智能回归检测 + AI 分析 + 依赖分析 |
| **CodeQL Analysis** | `.github/workflows/codeql-analysis.yml` | 安全漏洞 + 代码质量 (每周一 + push) |
| **Claude Code** | `.github/workflows/claude.yml` | Claude Code Action |

### Commit Analysis 工作流

```yaml
触发: push/PR 到 main
Jobs:
  1. Smart Regression Detection  # smart_commit_analyzer.py
     - 自动从 git 历史生成规则
     - 验证所有规则，检测回归
  2. AI Deep Analysis            # analyze_commits_ai.py (需要 DEEPSEEK_API_KEY)
     - DeepSeek 语义分析
     - 自动跳过 (如果没有 API key)
  3. Dependency Analysis         # analyze_dependencies.py
     - Python AST 依赖分析
     - 检测循环依赖和缺失模块
```

### CodeQL Analysis 工作流

```yaml
触发: push/PR 到 main + 每周一凌晨
功能:
  - 安全漏洞检测 (SQL注入、命令注入等)
  - 数据流分析 (追踪变量传递)
  - 代码质量检查
  - 自定义查询 (硬编码路径检测等)
```

### 设置 Secrets

在 GitHub 仓库设置中添加：
- `DEEPSEEK_API_KEY` - 启用 AI 深度分析 (可选)

## 联系方式

- GitHub: FelixWayne0318
- 仓库: https://github.com/FelixWayne0318/AItrader
