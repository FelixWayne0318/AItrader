# Web 架构分析与前后端职责划分

## 执行摘要

本文档分析 AlgVex Web 前后端当前架构，识别问题，并提出合理的前后端职责划分方案。

**关键发现**:
1. ✅ 核心架构合理：前后端分离、RESTful API、SWR 缓存
2. ⚠️ 部分数据源重复：`binance_service` vs `performance_service`
3. ⚠️ Config Service 职责过重：混合配置管理和系统运维
4. ⚠️ Risk Metrics 计算位置不当：应在后端计算

**修复状态**:
- [x] 统一 Performance 数据源
- [x] 拆分 System Service
- [ ] 重构 Risk Metrics 计算逻辑

---

## 1. 当前架构概览

### 1.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **Frontend** | Next.js 14 (React) + TypeScript | SSR/SSG 支持 |
| **State Management** | SWR (Stale-While-Revalidate) | 自动缓存和重验证 |
| **UI Components** | Radix UI + Tailwind CSS | 无障碍 + 响应式 |
| **Charts** | TradingView Widget | 专业图表组件 |
| **Backend** | FastAPI (Python 3.12) | 异步 API |
| **Database** | SQLite (aiosqlite) | 轻量级数据存储 |
| **ORM** | SQLAlchemy 2.0 (Async) | 数据模型管理 |
| **Performance Metrics** | empyrical-reloaded | 官方金融指标库 |

### 1.2 API 路由结构

```
/api/
├─ public/              # 公开访问 (无需认证)
│  ├─ performance       # 交易性能统计
│  ├─ ai-analysis       # AI 分析结果
│  ├─ signal-history    # 信号历史
│  ├─ social-links      # 社交媒体链接
│  └─ copy-trading      # 跟单链接
│
├─ trading/             # 实时市场数据 (部分需认证)
│  ├─ ticker/:symbol    # 实时价格
│  ├─ mark-price/:symbol # 标记价格
│  ├─ long-short-ratio  # 多空比
│  └─ orderbook/:symbol # 订单簿
│
├─ admin/               # 管理功能 (需 Google OAuth)
│  ├─ config            # 策略配置管理
│  ├─ service/control   # 服务控制 (restart/stop/start)
│  ├─ service/logs      # 日志查看
│  ├─ performance       # 详细性能数据
│  ├─ system/info       # 系统信息
│  └─ diagnostics       # 系统诊断
│
├─ auth/                # 认证
│  ├─ google/login      # Google OAuth 登录
│  └─ logout            # 登出
│
└─ ws/                  # WebSocket (未充分使用)
   └─ connect           # 实时推送连接
```

---

## 2. 问题分析

### 2.1 数据源重复 (已修复 ✅)

**问题**: `binance_service` 和 `performance_service` 都实现了 `get_performance_stats()`。

**风险**:
- 两个实现的计算逻辑可能不同
- Admin 和 Public API 返回不一致的数据
- `binance_service` 使用简化计算，`performance_service` 使用官方 empyrical 库

**修复**:
```python
# Before (admin.py)
from services import binance_service
stats = await binance_service.get_performance_stats(30)

# After (admin.py)
from services.performance_service import get_performance_service
service = get_performance_service()
stats = await service.get_performance_stats()
```

**影响**:
- ✅ 数据一致性保证
- ✅ 使用官方库计算，更准确
- ✅ 统一维护点

---

### 2.2 Config Service 职责过重 (已修复 ✅)

**问题**: `config_service.py` 混合了配置管理和系统运维功能。

**原职责**:
```
ConfigService (680 lines)
├─ 配置读写 (40%)
│  ├─ read_base_config()
│  ├─ write_base_config()
│  ├─ get_config_sections()
│  └─ update_config_value()
│
├─ 服务控制 (20%)  ← 应该独立
│  ├─ get_service_status()
│  ├─ restart_service()
│  ├─ stop_service()
│  └─ start_service()
│
├─ 日志管理 (10%)  ← 应该独立
│  ├─ get_recent_logs()
│  └─ get_log_file_content()
│
├─ 系统信息 (15%)  ← 应该独立
│  └─ get_system_info()
│
└─ 诊断 (15%)  ← 应该独立
   └─ run_diagnostics()
```

**安全风险**:
- 如果 Web 服务被攻击，攻击者可能通过 `/api/admin/service/control` 重启交易服务
- 没有审计日志 (谁在什么时候重启了服务？)
- 配置修改和服务控制混在一起，难以设置细粒度权限

**修复方案**: 拆分为两个服务

```
ConfigService (配置管理)
├─ read_base_config()
├─ write_base_config()
├─ get_config_sections()
└─ update_config_value()

SystemService (系统运维) - 新文件
├─ get_service_status()
├─ restart_service()
├─ stop_service()
├─ start_service()
├─ get_recent_logs()
├─ get_log_file_content()
├─ get_system_info()
└─ run_diagnostics()
```

**向后兼容**: `config_service` 保留所有现有方法，内部委托给 `system_service`。

---

### 2.3 Risk Metrics 计算位置不当 ⚠️

**当前实现**: Risk Metrics 在**后端**计算并返回。

**问题**:
```python
# admin.py:556-559
return {
    **stats,
    "risk_metrics": {  # ← 后端组装
        "sharpe_ratio": stats.get("sharpe_ratio", 0),
        "max_drawdown": stats.get("max_drawdown_percent", 0),
        "win_rate": stats.get("win_rate", 0),
    },
}
```

**分析**:

| 方案 | 优点 | 缺点 | 推荐? |
|------|------|------|-------|
| **后端计算** (当前) | - 数据一致性<br>- 减少前端计算负担 | - 字段重复 (stats 中已有这些值)<br>- 增加网络传输 | ✅ **推荐** |
| **前端计算** | - 减少数据传输<br>- 前端更灵活 | - 前端需要重新计算<br>- 可能不一致 | ❌ 不推荐 |

**结论**: **当前实现合理**，但可以优化：

**优化建议**: 移除 `risk_metrics` 包装器，直接使用 `stats` 中的字段。

```python
# Before (冗余)
{
  "sharpe_ratio": 1.5,
  "risk_metrics": {
    "sharpe_ratio": 1.5,  // 重复!
  }
}

# After (优化)
{
  "sharpe_ratio": 1.5,
  "sortino_ratio": 1.8,
  "max_drawdown_percent": -12.5,
}
```

**前端适配**:
```tsx
// Before
<div>{data.risk_metrics.sharpe_ratio}</div>

// After
<div>{data.sharpe_ratio}</div>
```

---

### 2.4 WebSocket 未充分利用 ⚠️

**问题**: Backend 有 `websocket_router`，但 Frontend 未使用。

**当前实现**:
```tsx
// chart.tsx - 使用 SWR 轮询
const { data: ticker } = useSWR("/api/trading/ticker/BTCUSDT", fetcher, {
  refreshInterval: 5000,  // 每 5 秒轮询一次
});
```

**WebSocket 优势**:
- 实时推送，无延迟
- 减少服务器负载 (无需频繁轮询)
- 双向通信

**建议使用场景**:
| 场景 | 当前方案 | WebSocket 优势 |
|------|----------|---------------|
| 实时价格 | SWR 5s 轮询 | 实时推送，0.1s 延迟 |
| AI 分析结果 | SWR 30s 轮询 | 分析完成立即推送 |
| 交易执行通知 | 无 | 订单成交立即通知 |
| 系统日志 (Admin) | 手动刷新 | 实时滚动显示 |

**实施建议**: Phase 2 优化项，当前 SWR 轮询已足够。

---

### 2.5 AI 分析数据缺失 ⚠️

**问题**: `/api/public/ai-analysis` 端点存在，但无数据。

**根因**: 交易机器人未写入 `logs/latest_analysis.json` 文件。

**数据流**:
```
策略 (deepseek_strategy.py)
  ↓
  AI 分析 (Bull/Bear/Judge)
  ↓
  ❌ 缺失: 写入 logs/latest_analysis.json
  ↓
Web API (public.py:225-275)
  ↓
  返回 NO_DATA
```

**修复方案** (不在本 PR 范围):
```python
# strategy/deepseek_strategy.py
async def _analyze_market_ai(self):
    # ... AI 分析逻辑 ...

    # 新增: 写入文件供 Web 使用
    import json
    from pathlib import Path

    analysis_data = {
        "signal": final_signal,
        "confidence": confidence,
        "bull_analysis": bull_reasoning,
        "bear_analysis": bear_reasoning,
        "judge_reasoning": judge_reasoning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log_file = Path("logs") / "latest_analysis.json"
    log_file.parent.mkdir(exist_ok=True)
    with open(log_file, "w") as f:
        json.dump(analysis_data, f, indent=2)
```

---

## 3. 前后端职责划分最佳实践

### 3.1 通用原则

| 职责 | 后端 (FastAPI) | 前端 (Next.js) |
|------|---------------|----------------|
| **数据获取** | ✅ 从数据库/外部 API 获取 | ❌ 不直接访问数据源 |
| **业务逻辑** | ✅ 核心业务规则 | ❌ 仅 UI 交互逻辑 |
| **数据验证** | ✅ 权威验证 (服务器端) | ⚠️ 辅助验证 (UX 优化) |
| **计算** | ✅ 复杂/敏感计算 | ⚠️ 简单格式化 |
| **权限控制** | ✅ 认证和授权 | ❌ 仅 UI 显示/隐藏 |
| **状态管理** | ⚠️ 持久化状态 (数据库) | ✅ 临时 UI 状态 (SWR/React) |
| **渲染** | ❌ (API only) | ✅ UI 组件 |
| **缓存** | ⚠️ 数据缓存 (Redis) | ✅ 请求缓存 (SWR) |

### 3.2 具体场景分析

#### Scenario 1: 性能指标计算

| 层级 | 职责 | 原因 |
|------|------|------|
| **后端** | ✅ 计算 Sharpe Ratio, Sortino, MDD | - 需要完整历史数据<br>- 计算复杂<br>- 使用官方库 (empyrical) |
| **前端** | ❌ 不应重新计算 | - 数据不完整<br>- 可能不一致 |
| **前端** | ✅ 格式化显示 (2 位小数) | - 纯展示逻辑 |

**当前实现**: ✅ 正确

```python
# Backend (performance_service.py)
sharpe_ratio = ep.sharpe_ratio(returns, annualization=365)
```

```tsx
// Frontend
<div>{data.sharpe_ratio.toFixed(2)}</div>
```

---

#### Scenario 2: 实时价格推送

| 层级 | 职责 | 原因 |
|------|------|------|
| **后端** | ✅ WebSocket 连接 Binance | - 需要 API 密钥<br>- 持久连接 |
| **后端** | ✅ 转发价格更新到前端 | - 数据中转 |
| **前端** | ✅ 接收 WebSocket 数据 | - 实时更新 UI |
| **前端** | ✅ 缓存最近价格 (React state) | - 平滑动画 |

**当前实现**: ⚠️ 使用 HTTP 轮询，建议改用 WebSocket

---

#### Scenario 3: 配置修改

| 层级 | 职责 | 原因 |
|------|------|------|
| **后端** | ✅ 验证配置值范围 | - 防止无效配置 |
| **后端** | ✅ 写入 base.yaml | - 文件系统访问 |
| **后端** | ✅ 检查权限 (Admin only) | - 安全控制 |
| **前端** | ✅ 表单验证 (UX) | - 即时反馈 |
| **前端** | ❌ 不直接写文件 | - 安全考虑 |

**当前实现**: ✅ 正确

```tsx
// Frontend - UX 验证
if (leverage < 1 || leverage > 125) {
  setError("Leverage must be 1-125");
}

// Backend - 权威验证
if not (1 <= leverage <= 125):
    raise HTTPException(400, "Invalid leverage")
```

---

#### Scenario 4: 交易信号展示

| 层级 | 职责 | 原因 |
|------|------|------|
| **后端** | ✅ 生成 AI 信号 | - AI 模型调用<br>- 复杂逻辑 |
| **后端** | ✅ 存储信号历史 | - 持久化 |
| **前端** | ✅ 获取最新信号 | - API 请求 |
| **前端** | ✅ 信号颜色映射 | - 纯 UI 逻辑 |
| **前端** | ❌ 不重新计算信号 | - 没有足够数据 |

**当前实现**: ✅ 正确

```tsx
// Frontend - UI 逻辑
const getSignalColor = (signal: string) => {
  if (signal === "BUY") return "text-green-500";
  if (signal === "SELL") return "text-red-500";
  return "text-gray-500";
};
```

---

#### Scenario 5: 时间格式化

| 层级 | 职责 | 原因 |
|------|------|------|
| **后端** | ✅ 返回 ISO 8601 格式 | - 标准化<br>- 时区明确 |
| **前端** | ✅ 本地化显示 | - 用户时区<br>- 国际化 |

**当前实现**: ✅ 正确

```python
# Backend
"timestamp": datetime.now(timezone.utc).isoformat()
# → "2026-02-14T02:30:00+00:00"
```

```tsx
// Frontend
const formatTime = (isoString: string) => {
  const date = new Date(isoString);  // 自动转换到用户时区
  return date.toLocaleString();
};
```

---

### 3.3 边界模糊场景

#### Scenario: 图表数据聚合 (K线 5m → 15m)

| 方案 | 优点 | 缺点 | 推荐? |
|------|------|------|-------|
| **后端聚合** | - 减少网络传输<br>- 统一逻辑 | - 增加服务器负载<br>- 灵活性低 | ⚠️ 看情况 |
| **前端聚合** | - 减轻服务器压力<br>- 用户切换时间框架快速 | - 需要传输原始数据<br>- 前端逻辑复杂 | ⚠️ 看情况 |

**建议**:
- 常用时间框架 (15m, 1h, 4h): 后端预聚合
- 用户自定义时间框架: 前端实时聚合

**当前实现**: ✅ 使用 TradingView Widget，由 TradingView 服务器处理

---

#### Scenario: 订单簿深度可视化

| 方案 | 优点 | 缺点 | 推荐? |
|------|------|------|-------|
| **后端处理** | - 计算 OBI、加权深度等 | - WebSocket 推送数据量大 | ✅ 推荐 |
| **前端处理** | - 灵活 | - 性能问题 | ❌ 不推荐 |

**建议**: 后端计算聚合指标 (OBI, Weighted OBI)，前端仅负责可视化。

---

## 4. 架构改进建议

### 4.1 短期优化 (Phase 2)

| 优先级 | 任务 | 影响 | 工作量 |
|--------|------|------|--------|
| **P0** | 移除 `risk_metrics` 包装器 | 减少数据冗余 | 1h |
| **P1** | 交易机器人写入 `latest_analysis.json` | 修复 AI 分析展示 | 2h |
| **P2** | Admin 添加操作审计日志 | 安全性 | 3h |

### 4.2 中期优化 (Phase 3)

| 优先级 | 任务 | 影响 | 工作量 |
|--------|------|------|--------|
| **P1** | WebSocket 实时价格推送 | 用户体验 | 5h |
| **P2** | 添加 Rate Limiting | 安全性 | 3h |
| **P3** | Frontend 状态管理 (Zustand) | 可维护性 | 4h |

### 4.3 长期优化 (Phase 4)

| 优先级 | 任务 | 影响 | 工作量 |
|--------|------|------|--------|
| **P1** | 引入 Redis 缓存 | 性能 | 8h |
| **P2** | API Gateway (Kong/Traefik) | 架构 | 10h |
| **P3** | 微服务拆分 | 可扩展性 | 20h+ |

---

## 5. 总结

### 5.1 当前架构优点

✅ **已做得好的地方**:
1. 清晰的前后端分离
2. RESTful API 设计合理
3. 使用官方库 (empyrical) 计算金融指标
4. SWR 缓存减少重复请求
5. Google OAuth 认证保护敏感操作

### 5.2 已修复问题

✅ **本 PR 完成**:
1. 统一 Performance 数据源 (使用 `performance_service`)
2. 拆分 System Service (增强安全性和可维护性)
3. 识别 AI 分析数据缺失问题

### 5.3 待改进项

⚠️ **后续 PR**:
1. 交易机器人写入 `latest_analysis.json`
2. 移除 `risk_metrics` 冗余包装
3. WebSocket 实时推送
4. Admin 操作审计日志

---

## 6. 参考资料

- [12-Factor App](https://12factor.net/)
- [REST API Best Practices](https://restfulapi.net/)
- [Frontend/Backend Separation Patterns](https://martinfowler.com/articles/micro-frontends.html)
- [SWR Documentation](https://swr.vercel.app/)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [empyrical Documentation](https://github.com/stefan-jansen/empyrical-reloaded)

---

**文档版本**: v1.0
**创建日期**: 2026-02-14
**作者**: Claude (Anthropic)
**审核**: Pending
