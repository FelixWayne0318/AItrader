---
name: code-review
description: |
  Multi-dimensional code review for bug detection, security, and architecture compliance. 多维度代码审查。

  Use this skill when:
  - Reviewing code changes before commit (提交前审查代码)
  - Reviewing pull requests (审查 PR)
  - Running pre-commit checks (运行预提交检查)
  - Checking for bugs, security issues, or architecture violations (检查 bugs、安全问题、架构违规)
  - Validating code against CLAUDE.md specifications (验证代码是否符合规范)

  Keywords: review, code, PR, bugs, security, architecture, commit, 审查, 代码, 安全
disable-model-invocation: true
---

# Code Review

Multi-dimensional code review based on Claude Code best practices.

## Review Modes

| Argument | Mode | Command |
|----------|------|---------|
| (empty) or `--staged` | staged | `git diff --cached` |
| `--unstaged` | unstaged | `git diff` |
| `--all` | all | `git diff HEAD` |
| `--pr <number>` | PR | `gh pr diff <number>` |
| `--commit <hash>` | commit | `git show <hash>` |
| `--branch` | branch | `git diff main...HEAD` |
| `--file <path>` | file | Read file directly |

## Review Dimensions

### 1. Bug Detection
- Logic errors, boundary conditions, null pointers, type errors
- Missing exception handling, resource leaks
- Concurrency issues, race conditions
- Hardcoded values, magic numbers

### 2. Security Review
- OWASP Top 10 vulnerabilities
- Missing input validation
- Sensitive data exposure (API keys, passwords, tokens)
- SQL/command injection risks
- Insecure dependencies

### 3. Architecture & Code Quality
- CLAUDE.md compliance
- Code style consistency
- Naming conventions
- Function complexity (warn if cyclomatic > 10)
- Code duplication, over-engineering

### 4. Project-Specific (AItrader)
- Stop-loss validation: LONG SL < entry, SHORT SL > entry
- API keys must be from environment variables
- Entry file must be `main_live.py`
- Telegram notification configuration
- Multi-agent divergence handling

## Confidence Scoring

| Score | Meaning | Action |
|-------|---------|--------|
| 0-49 | Possible false positive | Don't report |
| 50-79 | Medium confidence | List in "Suggestions" |
| 80-100 | High confidence | Must report |

**Default threshold: ≥80%**

## Output Format

```markdown
# Code Review Report

## Summary
- Review scope: [mode description]
- Files: N
- High confidence issues: N

## Issues Found

### 🔴 [Critical] Issue Title
- **File**: path/to/file.py:123
- **Confidence**: 95%
- **Type**: Bug | Security | Architecture | Project
- **Description**: Detailed description
- **Suggestion**: Fix recommendation

## Suggestions (50-79% confidence)
- Issue list

## Conclusion
✅ Review passed / ❌ Found N high-confidence issues
```

## Severity Levels

| Level | Icon | Confidence | Action |
|-------|------|------------|--------|
| Critical | 🔴 | ≥90% | Block merge |
| High | 🟠 | ≥85% | Should fix |
| Medium | 🟡 | ≥80% | Recommend fix |
| Low | 🔵 | ≥70% | Optional |

## Key Files

| File | Review Focus |
|------|--------------|
| `strategy/deepseek_strategy.py` | Stop-loss logic, signals, divergence |
| `utils/*.py` | API calls, error handling |
| `patches/*.py` | Compatibility, side effects |
| `main_live.py` | Config loading, initialization |
| `configs/base.yaml` | Base configuration (all parameters) |
| `configs/production.yaml` | Production environment overrides |

## 回归检测 (审查后必须运行)

```bash
# 智能回归检测 (规则自动从 git 历史生成)
python3 scripts/smart_commit_analyzer.py

# 预期结果: ✅ 所有规则验证通过
```
