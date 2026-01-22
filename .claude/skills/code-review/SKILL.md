---
name: code-review
description: 代码审查 - 多维度审查代码变更，检查 bugs、安全问题、架构合规性。Use for reviewing code changes, PR reviews, or pre-commit checks.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Task
  - WebFetch
---

# 代码审查 (Code Review)

基于 Claude Code 官方最佳实践的多维度代码审查技能。

## 审查模式

根据 `$ARGUMENTS` 选择审查模式：

| 参数 | 模式 | 描述 |
|------|------|------|
| (无参数) | staged | 审查暂存区的更改 (`git diff --cached`) |
| `--staged` | staged | 审查暂存区的更改 |
| `--unstaged` | unstaged | 审查未暂存的更改 (`git diff`) |
| `--all` | all | 审查所有更改 (staged + unstaged) |
| `--pr <number>` | PR | 审查指定 PR 的更改 |
| `--commit <hash>` | commit | 审查指定 commit 的更改 |
| `--branch` | branch | 审查当前分支与 main/master 的差异 |
| `--file <path>` | file | 审查指定文件 |

## 执行流程

### Step 1: 获取代码变更

```bash
# 根据模式获取 diff
# staged: git diff --cached
# unstaged: git diff
# all: git diff HEAD
# pr: gh pr diff <number>
# commit: git show <hash>
# branch: git diff main...HEAD 或 git diff master...HEAD
# file: 直接读取文件
```

### Step 2: 多维度审查 (并行执行)

启动 4 个独立的审查维度，使用 Task 工具并行执行：

#### 维度 1: Bug 检测 (Bug Scanner)
- 逻辑错误、边界条件、空指针、类型错误
- 异常处理缺失、资源泄漏
- 并发问题、竞态条件
- 硬编码值、魔法数字

#### 维度 2: 安全审查 (Security Reviewer)
- OWASP Top 10 漏洞
- 输入验证缺失
- 敏感信息泄露 (API keys, passwords)
- SQL/命令注入风险
- XSS/CSRF 漏洞
- 不安全的依赖

#### 维度 3: 架构与代码质量 (Architecture Reviewer)
- CLAUDE.md 规范合规性
- 代码风格一致性
- 命名规范
- 函数复杂度 (圈复杂度 > 10 警告)
- 重复代码
- 过度工程 / 设计过于复杂

#### 维度 4: 项目特定检查 (Project-Specific)
针对本项目的特定检查：
- 止损验证逻辑是否正确 (LONG: SL < entry, SHORT: SL > entry)
- API 密钥是否硬编码
- NautilusTrader API 使用是否正确
- Telegram 通知是否正确配置
- 策略参数是否合理

### Step 3: 置信度评分

每个发现的问题需要评估置信度 (0-100%):

| 分数 | 含义 | 报告阈值 |
|------|------|----------|
| 0-25 | 可能是误报 | 不报告 |
| 26-50 | 低置信度 | 仅 verbose 模式报告 |
| 51-79 | 中等置信度 | 标记为 "可能问题" |
| 80-100 | 高置信度 | 必须报告 |

**默认只报告置信度 ≥80% 的问题**

### Step 4: 输出格式

```markdown
# 代码审查报告

## 概要
- 审查范围: [staged/unstaged/PR #X/commit abc123]
- 文件数: X
- 问题数: Y (高置信度)

## 发现的问题

### [严重] 问题标题
- **文件**: path/to/file.py:123
- **置信度**: 95%
- **类型**: Bug/Security/Architecture/Project-Specific
- **描述**: 详细描述问题
- **建议**: 修复建议
- **代码片段**:
```python
# 问题代码
```

### [警告] 问题标题
...

## 建议改进 (低置信度)
- 列出置信度 50-79% 的问题，供参考

## 审查通过
如果没有高置信度问题，显示:
✅ 代码审查通过，未发现高置信度问题
```

## 严重级别定义

| 级别 | 图标 | 描述 | 置信度要求 |
|------|------|------|------------|
| Critical | 🔴 | 立即修复，阻止合并 | ≥90% |
| High | 🟠 | 应该修复 | ≥85% |
| Medium | 🟡 | 建议修复 | ≥80% |
| Low | 🔵 | 可选改进 | ≥70% |
| Info | ⚪ | 信息提示 | ≥50% |

## 常用命令示例

```bash
# 审查暂存区 (默认)
/code-review

# 审查所有更改
/code-review --all

# 审查 PR
/code-review --pr 123

# 审查特定文件
/code-review --file strategy/deepseek_strategy.py

# 审查当前分支
/code-review --branch
```

## 与 CLAUDE.md 的集成

审查时会检查以下 CLAUDE.md 规范：
1. 入口文件是否正确 (`main_live.py` 而非 `main.py`)
2. 止损逻辑是否符合规范
3. API 密钥是否使用环境变量
4. 服务配置是否正确

## 审查最佳实践

1. **提交前审查**: 每次 commit 前运行 `/code-review --staged`
2. **PR 审查**: 在合并前运行 `/code-review --pr <number>`
3. **定期审查**: 定期对关键模块进行全面审查
4. **关注高置信度**: 优先处理 ≥80% 置信度的问题

## 关键文件

| 文件 | 用途 |
|------|------|
| `CLAUDE.md` | 项目规范和最佳实践 |
| `strategy/deepseek_strategy.py` | 核心策略，重点审查 |
| `utils/*.py` | 工具模块 |
| `patches/*.py` | 补丁文件，注意兼容性 |

## 自动化集成

可以配合 Git hooks 使用：

```bash
# .git/hooks/pre-commit
#!/bin/bash
claude --skill code-review --staged
if [ $? -ne 0 ]; then
    echo "Code review failed. Please fix issues before committing."
    exit 1
fi
```
