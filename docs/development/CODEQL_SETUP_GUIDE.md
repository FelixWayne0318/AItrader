# CodeQL Code Scanning 设置指南

## 当前状态

CodeQL 分析工作流已配置并正常运行，但分析结果**无法上传到 GitHub**，因为仓库未启用 Code Scanning 功能。

## 错误信息

```
##[warning]Code scanning is not enabled for this repository.
Please enable code scanning in the repository settings.
```

## 解决方案

### 选项 1: 启用 Code Scanning (推荐) ✅

**需要**: 仓库管理员权限

**步骤**:

1. 进入仓库设置页面
   ```
   https://github.com/FelixWayne0318/AItrader/settings/security_analysis
   ```

2. 找到 **Code security and analysis** 部分

3. 在 **Code scanning** 区域点击 `Set up`

4. 选择 **Default** 或 **Advanced** 配置:
   - **Default**: GitHub 自动配置 (推荐新用户)
   - **Advanced**: 使用现有的 `.github/workflows/codeql-analysis.yml` (推荐本项目)

5. 如果选择 Advanced，确认使用现有配置文件

6. 保存设置

**完成后**:
- ✅ 后续 PR 提交将自动上传 CodeQL 结果
- ✅ 可在 **Security** 标签查看详细分析报告
- ✅ CI/CD 检查将显示绿色 ✓

### 选项 2: 临时禁用 CodeQL 上传 (不推荐)

如果暂时无法启用 Code Scanning，可以修改工作流仅保存 SARIF 文件：

**编辑** `.github/workflows/codeql-analysis.yml`:

```yaml
# 在 Perform CodeQL Analysis 步骤添加 upload: false
- name: Perform CodeQL Analysis
  uses: github/codeql-action/analyze@v3
  with:
    category: "/language:python"
    output: codeql-results
    upload: false  # 禁用上传
```

**缺点**:
- ❌ 无法在 Security 标签查看结果
- ❌ 无法跟踪历史漏洞趋势
- ❌ 失去 GitHub 提供的安全建议

### 选项 3: 完全禁用 CodeQL (不推荐)

如果完全不需要 CodeQL 分析：

**重命名工作流文件**:
```bash
# 在仓库设置中禁用工作流
# Settings > Actions > 找到 "CodeQL Analysis" > Disable workflow
```

## CodeQL 分析的价值

即使无法上传结果，CodeQL 仍然：
- ✅ 在 PR 中运行安全检查
- ✅ 生成 SARIF 文件 (可下载查看)
- ✅ 阻止包含高危安全问题的代码合并

## 相关文档

- [GitHub Code Scanning 文档](https://docs.github.com/en/code-security/code-scanning)
- [CodeQL 工作流配置](../../.github/workflows/codeql-analysis.yml)
- [自定义 CodeQL 查询](../../.github/codeql/custom-queries/)

## 当前工作流功能

即使未启用 Code Scanning，工作流仍会：

1. ✅ 扫描 Python 代码安全漏洞
2. ✅ 运行自定义查询 (硬编码路径检测等)
3. ✅ 生成 SARIF 报告文件 (可通过 Artifacts 下载)
4. ✅ 检测高危安全问题并阻止构建

唯一缺失的是将结果上传到 GitHub Security 标签的能力。

---

**推荐操作**: 启用 Code Scanning (选项 1)，这是 GitHub 免费提供的功能，能最大化安全保障。

## 故障排除

### 问题: "Code scanning is not enabled"

**解决**: 按照选项 1 的步骤启用 Code Scanning

### 问题: "refusing to allow a GitHub App to create or update workflow"

**原因**: GitHub Apps 默认没有修改 `.github/workflows/` 目录的权限

**解决**: 文档文件应放在 `docs/` 目录，不要放在 `.github/workflows/` 目录

### 问题: CodeQL 分析时间过长

**解决**:
- 使用 `schedule` 触发器，只在特定时间运行完整扫描
- 对 PR 使用增量分析 (GitHub 自动优化)

## 参考链接

- [GitHub Actions and CI/CD 开发指南](./GITHUB_ACTIONS_GUIDE.md)
- [CodeQL Documentation](https://codeql.github.com/docs/)
- [Python CodeQL Queries](https://github.com/github/codeql/tree/main/python/ql/src)
