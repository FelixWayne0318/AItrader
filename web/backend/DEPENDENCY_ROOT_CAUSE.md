# Web Backend Dependency Root Cause Analysis

**Issue**: Backend repeatedly crashes with `TypeError: deprecate_kwarg() missing 1 required positional argument: 'new_arg_name'`

**Date**: 2026-02-14
**Status**: **PERMANENTLY FIXED** (v3.0.2)

---

## 🔍 Deep Root Cause Analysis

### The Problem Chain

```
performance_service.py
  ↓ import empyrical (line 28)
  ↓
empyrical/__init__.py
  ↓ imports empyrical.stats
  ↓
empyrical/stats.py
  ↓ imports empyrical.utils
  ↓
empyrical/utils.py
  ↓ import pandas_datareader (line 27)
  ↓
pandas_datareader/__init__.py
  ↓ imports pandas_datareader.data
  ↓
pandas_datareader/data.py
  ↓ @deprecate_kwarg("access_key", "api_key") [line 273]
  ↓
CRASH: TypeError - old pandas decorator syntax incompatible with Python 3.12
```

### Why It Keeps Recurring

**每次部署时发生的事情** (What happens on every deployment):

1. `git pull` 拉取最新代码
2. 运行 `pip install -r requirements.txt`
3. `empyrical>=0.5.5` 被安装
4. `empyrical` **强制依赖** `pandas-datareader`
5. `pandas-datareader` 与 Python 3.12 **不兼容**
6. 后端启动 → 导入失败 → 崩溃

**即使修复了代码，只要 `requirements.txt` 使用 `empyrical`，下次部署仍会重现！**

---

## 📊 Root Cause Comparison

| 包名 | 维护状态 | Python 3.12 支持 | pandas-datareader 依赖 | 最后更新 |
|------|---------|-----------------|----------------------|---------|
| `empyrical` (原版) | ❌ **已废弃** | ❌ **不兼容** | ✅ **强制依赖** (导致崩溃) | 2019年 |
| `empyrical-reloaded` | ✅ **活跃维护** | ✅ **完全支持** | ⚠️ **可选依赖** (不自动安装) | 2026年 |

### 关键差异

**empyrical (原版)**:
```python
# setup.py
install_requires = [
    'pandas-datareader',  # 强制安装
    'pandas',
    ...
]
```
→ 每次安装 `empyrical` 都会安装 `pandas-datareader`
→ Python 3.12 崩溃

**empyrical-reloaded**:
```python
# setup.py
install_requires = [
    'pandas',
    ...
]
extras_require = {
    'dev': ['pandas-datareader'],  # 可选依赖
}
```
→ 默认不安装 `pandas-datareader`
→ 避免依赖冲突

---

## ✅ Permanent Fix (v3.0.2)

### 修改 1: requirements.txt

**错误配置** (导致反复崩溃):
```python
empyrical>=0.5.5  # 原版，已废弃
```

**正确配置** (永久修复):
```python
empyrical-reloaded>=0.5.12,<1.0  # Python 3.12 compatible
pandas>=2.2.2,<4.0               # Required for numpy>=2.0
```

### 修改 2: performance_service.py

添加清晰的注释说明为什么使用 `empyrical-reloaded`:

```python
# CRITICAL: Use empyrical-reloaded (Python 3.12 compatible), NOT empyrical (unmaintained)
try:
    import empyrical as ep
    EMPYRICAL_AVAILABLE = True
except ImportError:
    EMPYRICAL_AVAILABLE = False
    logging.warning("empyrical-reloaded not installed. Run: pip install empyrical-reloaded>=0.5.12")
```

### 修改 3: 版本约束

添加上限约束防止未来不兼容：

```python
empyrical-reloaded>=0.5.12,<1.0  # Pin major version
scipy>=1.9.0,<2.0                # Pin major version
statsmodels>=0.14.0,<1.0         # Pin major version
pandas>=2.2.2,<4.0               # Compatible with numpy>=2.0
numpy>=1.24.0,<3.0               # Pin major version
```

---

## 🚀 Deployment Instructions

### 服务器部署步骤

```bash
# 1. 拉取代码
cd /home/linuxuser/nautilus_AItrader
git pull origin main

# 2. 进入 backend 目录
cd web/backend

# 3. 停止后端服务
pm2 stop algvex-backend

# 4. 激活虚拟环境
source venv/bin/activate

# 5. 卸载旧包 (关键!)
pip uninstall -y empyrical pandas-datareader

# 6. 安装新依赖
pip install -r requirements.txt

# 7. 验证安装
python -c "import empyrical; print(f'empyrical version: {empyrical.__version__}')"
python -c "import sys; print(f'Python version: {sys.version}')"

# 8. 重启后端
pm2 restart algvex-backend

# 9. 检查日志
pm2 logs algvex-backend --lines 50
```

### 一键修复脚本

创建 `web/backend/fix_dependencies.sh`:

```bash
#!/bin/bash
set -e

echo "=== Web Backend Dependency Fix (v3.0.2) ==="
cd /home/linuxuser/nautilus_AItrader/web/backend

# Stop backend
pm2 stop algvex-backend || true

# Activate venv
source venv/bin/activate

# Uninstall problematic packages
echo "Removing old empyrical and pandas-datareader..."
pip uninstall -y empyrical pandas-datareader || true

# Install new dependencies
echo "Installing empyrical-reloaded..."
pip install -r requirements.txt

# Verify
echo "=== Verification ==="
python -c "import empyrical; print(f'✅ empyrical version: {empyrical.__version__}')"
python -c "import sys; print(f'✅ Python version: {sys.version}')"

# Restart
pm2 restart algvex-backend

echo "=== Done! Checking logs... ==="
pm2 logs algvex-backend --lines 20
```

---

## 📚 References

- [empyrical-reloaded PyPI](https://pypi.org/project/empyrical-reloaded/)
- [empyrical-reloaded GitHub](https://github.com/stefan-jansen/empyrical-reloaded)
- [pandas-datareader Python 3.12 incompatibility](https://github.com/quantopian/empyrical/issues/110)
- [pandas 3.0 changelog](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html)

---

## 🎯 Lessons Learned

### 为什么之前的修复都失效？

1. **表面修复**: 修改代码、重启服务、清理缓存
2. **根因未除**: `requirements.txt` 仍使用 `empyrical`
3. **下次部署**: `pip install` 重新安装旧包 → 问题重现

### 正确的问题解决流程

1. **识别症状**: Backend 崩溃，`TypeError` in pandas_datareader
2. **追踪根因**: 依赖链 → `empyrical` → `pandas-datareader` → 不兼容
3. **调研方案**: 搜索 `empyrical Python 3.12` → 发现 `empyrical-reloaded`
4. **永久修复**: 修改依赖声明 + 添加版本约束
5. **文档记录**: 创建此文档，防止未来重蹈覆辙

### 关键教训

- **Don't just fix symptoms - find the root cause**
  不要只修复症状 - 找到根本原因

- **Check dependency maintenance status**
  检查依赖的维护状态

- **Pin dependency versions with upper bounds**
  用上限约束固定依赖版本

- **Document WHY, not just WHAT**
  记录"为什么"，不仅仅是"做了什么"

---

**Date Created**: 2026-02-14
**Author**: Claude Sonnet 4.5
**Version**: v3.0.2
