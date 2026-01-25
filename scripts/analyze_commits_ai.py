#!/usr/bin/env python3
"""
AI 增强的 Git 提交分析器
========================

利用 DeepSeek/Claude API 进行语义级别的提交分析。

与 analyze_git_changes.py (正则匹配) 的区别:
- 使用 LLM 理解 commit message 的真实意图
- 从 diff 语义推断修复了什么问题
- 生成更精确的验证规则
- 识别潜在的回归风险

用法:
    python3 analyze_commits_ai.py --commits 10           # 分析最近 10 个提交
    python3 analyze_commits_ai.py --commit abc1234      # 分析单个提交
    python3 analyze_commits_ai.py --check               # 运行 AI 生成的回归检测
    python3 analyze_commits_ai.py --generate-validators # 生成验证器代码
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# =============================================================================
# 颜色输出
# =============================================================================
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.RESET}\n")

def print_section(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}[{text}]{Colors.RESET}")
    print("-" * 60)

def print_ok(text: str):
    print(f"  {Colors.GREEN}✅ {text}{Colors.RESET}")

def print_warn(text: str):
    print(f"  {Colors.YELLOW}⚠️  {text}{Colors.RESET}")

def print_error(text: str):
    print(f"  {Colors.RED}❌ {text}{Colors.RESET}")

def print_info(text: str):
    print(f"  ℹ️  {text}")


# =============================================================================
# 数据结构
# =============================================================================
@dataclass
class AICommitAnalysis:
    """AI 分析结果"""
    commit_hash: str
    short_hash: str
    message: str

    # AI 推断的信息
    fix_type: str = ""           # bug_fix, feature, refactor, security, config, docs
    severity: str = "low"        # critical, high, medium, low
    category: str = ""           # threading, config, api, architecture, etc.

    # AI 生成的描述
    problem_fixed: str = ""      # 修复了什么问题
    root_cause: str = ""         # 根本原因
    solution: str = ""           # 解决方案

    # 验证信息
    validation_rules: List[Dict[str, str]] = field(default_factory=list)
    regression_risks: List[str] = field(default_factory=list)
    affected_components: List[str] = field(default_factory=list)

    # 原始数据
    files_changed: List[str] = field(default_factory=list)
    key_changes: List[str] = field(default_factory=list)


# =============================================================================
# Git 操作
# =============================================================================
class GitHelper:
    """Git 辅助类"""

    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path(__file__).parent

    def run(self, *args) -> str:
        cmd = ['git', '-C', str(self.repo_path)] + list(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        except Exception:
            return ""

    def get_commits(self, limit: int = 10) -> List[Dict[str, str]]:
        output = self.run('log', f'-n{limit}', '--format=%H|%h|%s', '--no-merges')
        commits = []
        for line in output.strip().split('\n'):
            if '|' in line:
                parts = line.split('|', 2)
                if len(parts) >= 3:
                    commits.append({
                        'hash': parts[0],
                        'short_hash': parts[1],
                        'message': parts[2],
                    })
        return commits

    def get_diff(self, commit_hash: str) -> str:
        return self.run('show', '--format=', '--patch', commit_hash)

    def get_files(self, commit_hash: str) -> List[str]:
        output = self.run('show', '--format=', '--name-only', commit_hash)
        return [f for f in output.strip().split('\n') if f]

    def get_file_content(self, file_path: str) -> str:
        full_path = self.repo_path / file_path
        if full_path.exists():
            return full_path.read_text(encoding='utf-8', errors='ignore')
        return ""


# =============================================================================
# AI 分析器
# =============================================================================
class AIAnalyzer:
    """使用 LLM 进行语义分析"""

    ANALYSIS_PROMPT = '''分析以下 Git 提交，以 JSON 格式返回分析结果。

Commit Hash: {short_hash}
Commit Message: {message}
Files Changed: {files}

Diff (部分):
```
{diff_preview}
```

请分析并返回以下 JSON 格式（只返回 JSON，不要其他文字）:
{{
    "fix_type": "bug_fix|feature|refactor|security|config|docs|test",
    "severity": "critical|high|medium|low",
    "category": "threading|config|api|architecture|compatibility|ui|bugfix|other",
    "problem_fixed": "用一句话描述修复了什么问题",
    "root_cause": "问题的根本原因",
    "solution": "解决方案概述",
    "validation_rules": [
        {{
            "type": "code_exists|code_not_exists|pattern_match",
            "file": "文件路径",
            "check": "要检查的代码片段或正则模式",
            "description": "验证描述"
        }}
    ],
    "regression_risks": ["可能的回归风险1", "可能的回归风险2"],
    "affected_components": ["影响的组件1", "影响的组件2"],
    "key_changes": ["关键变更1", "关键变更2"]
}}

注意:
1. validation_rules 应该是可以自动验证的规则
2. 如果是 bug_fix，severity 通常至少是 medium
3. threading 相关问题通常是 critical
4. 只返回 JSON，不要解释'''

    def __init__(self, api_key: str = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("需要设置 DEEPSEEK_API_KEY")
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com"
            )
        return self._client

    def analyze_commit(self,
                      commit: Dict[str, str],
                      diff: str,
                      files: List[str]) -> AICommitAnalysis:
        """分析单个提交"""

        # 截取 diff 预览 (避免 token 过多)
        diff_preview = diff[:4000] if len(diff) > 4000 else diff

        prompt = self.ANALYSIS_PROMPT.format(
            short_hash=commit['short_hash'],
            message=commit['message'],
            files=', '.join(files[:10]),
            diff_preview=diff_preview,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )

            content = response.choices[0].message.content.strip()

            # 提取 JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            data = json.loads(content)

            return AICommitAnalysis(
                commit_hash=commit['hash'],
                short_hash=commit['short_hash'],
                message=commit['message'],
                fix_type=data.get('fix_type', 'unknown'),
                severity=data.get('severity', 'low'),
                category=data.get('category', 'other'),
                problem_fixed=data.get('problem_fixed', ''),
                root_cause=data.get('root_cause', ''),
                solution=data.get('solution', ''),
                validation_rules=data.get('validation_rules', []),
                regression_risks=data.get('regression_risks', []),
                affected_components=data.get('affected_components', []),
                files_changed=files,
                key_changes=data.get('key_changes', []),
            )

        except Exception as e:
            print_warn(f"AI 分析失败 ({commit['short_hash']}): {e}")
            return AICommitAnalysis(
                commit_hash=commit['hash'],
                short_hash=commit['short_hash'],
                message=commit['message'],
                files_changed=files,
            )


# =============================================================================
# 回归检测器
# =============================================================================
class AIRegressionChecker:
    """基于 AI 生成的规则进行回归检测"""

    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path(__file__).parent
        self.git = GitHelper(repo_path)

    def check_rule(self, rule: Dict[str, str]) -> Dict[str, Any]:
        """检查单个验证规则"""
        result = {
            'rule': rule,
            'passed': False,
            'details': '',
        }

        file_path = rule.get('file', '')
        check_type = rule.get('type', 'code_exists')
        check_value = rule.get('check', '')

        if not file_path or not check_value:
            result['details'] = '规则不完整'
            return result

        content = self.git.get_file_content(file_path)

        if not content:
            result['details'] = f'文件不存在: {file_path}'
            return result

        if check_type == 'code_exists':
            # 规范化空白后比较
            normalized_content = ' '.join(content.split())
            normalized_check = ' '.join(check_value.split())
            result['passed'] = normalized_check in normalized_content
            result['details'] = '代码存在' if result['passed'] else '代码不存在'

        elif check_type == 'code_not_exists':
            normalized_content = ' '.join(content.split())
            normalized_check = ' '.join(check_value.split())
            result['passed'] = normalized_check not in normalized_content
            result['details'] = '代码不存在 (正确)' if result['passed'] else '问题代码仍存在!'

        elif check_type == 'pattern_match':
            import re
            try:
                result['passed'] = bool(re.search(check_value, content))
                result['details'] = '模式匹配' if result['passed'] else '模式不匹配'
            except re.error as e:
                result['details'] = f'正则错误: {e}'

        return result

    def check_analysis(self, analysis: AICommitAnalysis) -> List[Dict[str, Any]]:
        """检查分析结果中的所有验证规则"""
        results = []

        for rule in analysis.validation_rules:
            result = self.check_rule(rule)
            result['commit'] = analysis.short_hash
            result['severity'] = analysis.severity
            results.append(result)

        return results


# =============================================================================
# 验证器代码生成器
# =============================================================================
class ValidatorGenerator:
    """生成 validate_commit_fixes.py 兼容的验证器代码"""

    @staticmethod
    def generate(analysis: AICommitAnalysis) -> str:
        """生成验证器注册表条目"""

        validators = []
        for rule in analysis.validation_rules:
            check_type = rule.get('type', 'code_exists')
            check_value = rule.get('check', '').replace("'", "\\'")

            if check_type == 'code_exists':
                validators.append(f"lambda content, **_: '{check_value}' in content")
            elif check_type == 'code_not_exists':
                validators.append(f"lambda content, **_: '{check_value}' not in content")
            elif check_type == 'pattern_match':
                validators.append(f"lambda content, **_: bool(re.search(r'{check_value}', content))")

        files = [rule.get('file', '') for rule in analysis.validation_rules if rule.get('file')]
        files = list(set(files))  # 去重

        if not validators or not files:
            return ""

        code = f'''    {{
        'id': '{analysis.short_hash}-{analysis.category}',
        'commit': '{analysis.short_hash}',
        'category': '{analysis.category}',
        'description': '{analysis.problem_fixed[:60]}',
        'files': {files},
        'validators': [
            {(','+chr(10)+'            ').join(validators)},
        ],
        'error_msg': '{analysis.problem_fixed[:80]}',
        'fix_hint': '{analysis.solution[:80]}',
        'severity': '{analysis.severity}',
    }},'''

        return code


# =============================================================================
# 主程序
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description='AI 增强的 Git 提交分析器'
    )
    parser.add_argument('--commits', '-n', type=int, default=5,
                       help='分析最近 N 个提交')
    parser.add_argument('--commit', '-c', type=str,
                       help='分析单个提交')
    parser.add_argument('--check', action='store_true',
                       help='运行回归检测')
    parser.add_argument('--generate-validators', action='store_true',
                       help='生成验证器代码')
    parser.add_argument('--json', action='store_true',
                       help='JSON 输出')
    parser.add_argument('--fix-only', action='store_true',
                       help='只分析 fix 类型的提交')

    args = parser.parse_args()

    # 检查 API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print_error("需要设置 DEEPSEEK_API_KEY 环境变量")
        print_info("export DEEPSEEK_API_KEY=your_key")
        return 1

    if not args.json:
        print_header("AI 增强的 Git 提交分析器")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  模型: DeepSeek Chat")

    git = GitHelper()
    analyzer = AIAnalyzer()
    checker = AIRegressionChecker()

    # 获取提交
    if args.commit:
        commits = [{'hash': args.commit, 'short_hash': args.commit[:7],
                   'message': git.run('log', '-1', '--format=%s', args.commit).strip()}]
    else:
        commits = git.get_commits(limit=args.commits)

    if not args.json:
        print_section(f"分析 {len(commits)} 个提交")

    analyses = []
    all_check_results = []

    for i, commit in enumerate(commits):
        if not args.json:
            print_info(f"[{i+1}/{len(commits)}] 分析 {commit['short_hash']}: {commit['message'][:50]}...")

        diff = git.get_diff(commit['hash'])
        files = git.get_files(commit['hash'])

        analysis = analyzer.analyze_commit(commit, diff, files)

        # 过滤非 fix 类型
        if args.fix_only and analysis.fix_type != 'bug_fix':
            continue

        analyses.append(analysis)

        # 运行回归检测
        if args.check and analysis.validation_rules:
            results = checker.check_analysis(analysis)
            all_check_results.extend(results)

    # 输出结果
    if args.json:
        output = {
            'analyses': [asdict(a) for a in analyses],
            'check_results': all_check_results if args.check else [],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    # 打印分析结果
    print_section("分析结果")

    for analysis in analyses:
        severity_color = (Colors.RED if analysis.severity == 'critical'
                        else Colors.YELLOW if analysis.severity == 'high'
                        else Colors.RESET)

        print(f"\n  {Colors.BOLD}{analysis.short_hash}{Colors.RESET} "
              f"[{severity_color}{analysis.severity}{Colors.RESET}] "
              f"[{analysis.fix_type}]")
        print(f"    消息: {analysis.message[:60]}")

        if analysis.problem_fixed:
            print(f"    问题: {analysis.problem_fixed}")
        if analysis.root_cause:
            print(f"    原因: {analysis.root_cause}")
        if analysis.solution:
            print(f"    方案: {analysis.solution}")

        if analysis.regression_risks:
            print(f"    {Colors.YELLOW}回归风险:{Colors.RESET}")
            for risk in analysis.regression_risks[:3]:
                print(f"      - {risk}")

        if analysis.validation_rules:
            print(f"    验证规则: {len(analysis.validation_rules)} 条")

    # 回归检测结果
    if args.check and all_check_results:
        print_section("回归检测结果")

        passed = sum(1 for r in all_check_results if r['passed'])
        failed = len(all_check_results) - passed

        if failed == 0:
            print_ok(f"全部通过! {passed}/{len(all_check_results)}")
        else:
            print_warn(f"通过: {passed}/{len(all_check_results)}")
            print_error(f"失败: {failed}")

            for r in all_check_results:
                if not r['passed']:
                    print(f"    ❌ [{r['severity']}] {r['commit']}: {r['rule'].get('description', '')}")

    # 生成验证器代码
    if args.generate_validators:
        print_section("生成的验证器代码")
        print("\n# 添加到 validate_commit_fixes.py 的 COMMIT_FIX_REGISTRY:\n")

        for analysis in analyses:
            if analysis.fix_type == 'bug_fix' and analysis.validation_rules:
                code = ValidatorGenerator.generate(analysis)
                if code:
                    print(code)
                    print()

    # 总结
    print_section("总结")

    fix_count = sum(1 for a in analyses if a.fix_type == 'bug_fix')
    critical_count = sum(1 for a in analyses if a.severity == 'critical')

    print_info(f"分析了 {len(analyses)} 个提交")
    print_info(f"  - Bug 修复: {fix_count}")
    print_info(f"  - 严重级别: {critical_count}")

    if args.check:
        if all_check_results:
            pass_rate = passed / len(all_check_results) * 100
            print_info(f"  - 回归检测通过率: {pass_rate:.0f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
