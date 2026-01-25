#!/usr/bin/env python3
"""
Git 变更自动分析器 (Automatic Git Change Analyzer)
===================================================

全自动分析 Git 提交历史，推断每个提交修复了什么问题，
并生成验证规则检测潜在的回归。

核心功能:
1. 读取 Git 提交历史 (git log)
2. 分析每个提交的 diff (git show)
3. 从 commit message 和 diff 推断修复意图
4. 自动生成验证规则
5. 检测潜在的回归和连锁反应

用法:
    python3 analyze_git_changes.py                    # 分析所有提交
    python3 analyze_git_changes.py --since "1 week"   # 最近一周
    python3 analyze_git_changes.py --commits 50       # 最近 50 个提交
    python3 analyze_git_changes.py --check            # 运行回归检测
    python3 analyze_git_changes.py --report           # 生成详细报告
    python3 analyze_git_changes.py --json             # JSON 输出
"""

import os
import sys
import re
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict

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
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
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
    print(f"  {Colors.WHITE}ℹ️  {text}{Colors.RESET}")


# =============================================================================
# 数据结构
# =============================================================================
@dataclass
class CodeChange:
    """代码变更"""
    file_path: str
    added_lines: List[str] = field(default_factory=list)
    removed_lines: List[str] = field(default_factory=list)
    added_line_numbers: List[int] = field(default_factory=list)
    removed_line_numbers: List[int] = field(default_factory=list)


@dataclass
class CommitAnalysis:
    """提交分析结果"""
    commit_hash: str
    short_hash: str
    author: str
    date: str
    message: str

    # 推断的信息
    commit_type: str = "unknown"  # fix, feat, refactor, docs, test, chore
    severity: str = "low"  # critical, high, medium, low
    category: str = "unknown"  # threading, config, api, architecture, bugfix

    # 变更信息
    files_changed: List[str] = field(default_factory=list)
    code_changes: List[CodeChange] = field(default_factory=list)

    # 关键代码片段 (用于验证)
    key_additions: List[str] = field(default_factory=list)
    key_removals: List[str] = field(default_factory=list)

    # 潜在问题
    potential_issues: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class RegressionCheck:
    """回归检测结果"""
    commit_hash: str
    description: str
    check_type: str  # code_exists, code_removed, pattern_match
    file_path: str
    expected: str
    actual: str
    passed: bool
    severity: str


# =============================================================================
# Git 操作
# =============================================================================
class GitAnalyzer:
    """Git 分析器"""

    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path(__file__).parent

    def run_git(self, *args) -> str:
        """运行 git 命令"""
        cmd = ['git', '-C', str(self.repo_path)] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            return ""

    def get_commits(self,
                    since: str = None,
                    limit: int = None,
                    branch: str = None) -> List[Dict[str, str]]:
        """获取提交列表"""
        args = ['log', '--format=%H|%h|%an|%ad|%s', '--date=short']

        if since:
            args.append(f'--since="{since}"')
        if limit:
            args.append(f'-n{limit}')
        if branch:
            args.append(branch)

        output = self.run_git(*args)

        commits = []
        for line in output.strip().split('\n'):
            if '|' in line:
                parts = line.split('|', 4)
                if len(parts) >= 5:
                    commits.append({
                        'hash': parts[0],
                        'short_hash': parts[1],
                        'author': parts[2],
                        'date': parts[3],
                        'message': parts[4],
                    })

        return commits

    def get_commit_diff(self, commit_hash: str) -> str:
        """获取提交的 diff"""
        return self.run_git('show', '--format=', '--patch', commit_hash)

    def get_commit_files(self, commit_hash: str) -> List[str]:
        """获取提交影响的文件"""
        output = self.run_git('show', '--format=', '--name-only', commit_hash)
        return [f for f in output.strip().split('\n') if f]

    def get_file_content(self, file_path: str, commit_hash: str = 'HEAD') -> str:
        """获取指定版本的文件内容"""
        return self.run_git('show', f'{commit_hash}:{file_path}')

    def get_current_file_content(self, file_path: str) -> str:
        """获取当前工作目录的文件内容"""
        full_path = self.repo_path / file_path
        if full_path.exists():
            return full_path.read_text(encoding='utf-8', errors='ignore')
        return ""


# =============================================================================
# 提交分析器
# =============================================================================
class CommitTypeAnalyzer:
    """提交类型分析器 - 从 commit message 推断类型"""

    # Conventional Commits 模式
    COMMIT_PATTERNS = {
        'fix': r'^fix[\(:]|bug|修复|修正|解决',
        'feat': r'^feat[\(:]|feature|新增|添加|实现',
        'refactor': r'^refactor[\(:]|重构|优化|改进',
        'docs': r'^docs[\(:]|文档|readme|comment',
        'test': r'^test[\(:]|测试',
        'chore': r'^chore[\(:]|杂项|配置',
        'perf': r'^perf[\(:]|性能|优化',
        'security': r'security|安全|漏洞|xss|sql|injection',
    }

    # 严重程度关键词
    SEVERITY_KEYWORDS = {
        'critical': ['panic', 'crash', 'fatal', 'security', 'data loss', '崩溃', '严重'],
        'high': ['bug', 'fix', 'error', 'exception', 'fail', '错误', '问题'],
        'medium': ['improve', 'update', 'change', 'refactor', '优化', '改进'],
        'low': ['docs', 'style', 'chore', 'test', '文档', '测试'],
    }

    # 类别关键词
    CATEGORY_KEYWORDS = {
        'threading': ['thread', 'async', 'lock', 'mutex', 'concurrent', 'race', '线程', '异步'],
        'config': ['config', 'setting', 'parameter', 'yaml', 'env', '配置', '参数'],
        'api': ['api', 'endpoint', 'request', 'response', 'http', 'binance', 'deepseek'],
        'architecture': ['architecture', 'structure', 'design', 'pattern', '架构', '设计'],
        'compatibility': ['compatibility', 'version', 'upgrade', 'migrate', '兼容', '版本'],
        'ui': ['telegram', 'notification', 'message', 'display', '通知', '显示'],
    }

    @classmethod
    def analyze(cls, message: str, diff: str = "") -> Tuple[str, str, str]:
        """
        分析提交类型、严重程度和类别

        Returns:
            (commit_type, severity, category)
        """
        message_lower = message.lower()
        diff_lower = diff.lower() if diff else ""
        combined = message_lower + " " + diff_lower

        # 推断类型
        commit_type = 'unknown'
        for ctype, pattern in cls.COMMIT_PATTERNS.items():
            if re.search(pattern, message_lower, re.IGNORECASE):
                commit_type = ctype
                break

        # 推断严重程度
        severity = 'low'
        for sev, keywords in cls.SEVERITY_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                severity = sev
                break

        # 推断类别
        category = 'bugfix' if commit_type == 'fix' else 'unknown'
        for cat, keywords in cls.CATEGORY_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                category = cat
                break

        return commit_type, severity, category


# =============================================================================
# Diff 解析器
# =============================================================================
class DiffParser:
    """Diff 解析器"""

    @staticmethod
    def parse(diff_text: str) -> List[CodeChange]:
        """解析 git diff 输出"""
        changes = []
        current_file = None
        current_change = None

        for line in diff_text.split('\n'):
            # 新文件开始
            if line.startswith('diff --git'):
                if current_change:
                    changes.append(current_change)
                # 提取文件路径
                match = re.search(r'b/(.+)$', line)
                if match:
                    current_file = match.group(1)
                    current_change = CodeChange(file_path=current_file)

            # 添加的行
            elif line.startswith('+') and not line.startswith('+++'):
                if current_change:
                    current_change.added_lines.append(line[1:])

            # 删除的行
            elif line.startswith('-') and not line.startswith('---'):
                if current_change:
                    current_change.removed_lines.append(line[1:])

        # 添加最后一个
        if current_change:
            changes.append(current_change)

        return changes


# =============================================================================
# 关键代码提取器
# =============================================================================
class KeyCodeExtractor:
    """提取关键代码片段 - 用于生成验证规则"""

    # 重要的代码模式
    IMPORTANT_PATTERNS = [
        # 函数/方法定义
        r'^\s*def\s+(\w+)',
        r'^\s*async\s+def\s+(\w+)',
        # 类定义
        r'^\s*class\s+(\w+)',
        # 导入语句
        r'^from\s+(\S+)\s+import',
        r'^import\s+(\S+)',
        # 常量定义
        r'^([A-Z_]+)\s*=',
        # 配置键
        r"config.*\.get\(['\"](\w+)['\"]",
        # 特殊方法调用
        r'\.(lock|unlock|acquire|release)\(',
        r'threading\.(Lock|RLock|Event)',
        # 错误处理
        r'except\s+(\w+)',
        r'raise\s+(\w+)',
    ]

    @classmethod
    def extract_key_code(cls,
                        added_lines: List[str],
                        removed_lines: List[str]) -> Tuple[List[str], List[str]]:
        """
        提取关键代码片段

        Returns:
            (key_additions, key_removals)
        """
        key_additions = []
        key_removals = []

        for line in added_lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('#'):
                continue

            # 检查是否匹配重要模式
            for pattern in cls.IMPORTANT_PATTERNS:
                if re.search(pattern, line):
                    key_additions.append(line_stripped)
                    break
            else:
                # 包含特定关键词的行也很重要
                important_keywords = [
                    'return', 'raise', 'assert', 'if __name__',
                    'self.', 'cls.', 'super()', '@',
                ]
                if any(kw in line for kw in important_keywords):
                    if len(line_stripped) > 10:  # 过滤太短的行
                        key_additions.append(line_stripped)

        for line in removed_lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('#'):
                continue

            for pattern in cls.IMPORTANT_PATTERNS:
                if re.search(pattern, line):
                    key_removals.append(line_stripped)
                    break

        # 去重并限制数量
        key_additions = list(dict.fromkeys(key_additions))[:20]
        key_removals = list(dict.fromkeys(key_removals))[:20]

        return key_additions, key_removals


# =============================================================================
# 依赖分析器
# =============================================================================
class DependencyAnalyzer:
    """分析文件依赖关系"""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._import_graph: Dict[str, Set[str]] = {}

    def build_import_graph(self):
        """构建导入关系图"""
        for py_file in self.repo_path.rglob("*.py"):
            if '__pycache__' in str(py_file):
                continue

            relative_path = str(py_file.relative_to(self.repo_path))
            self._import_graph[relative_path] = set()

            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')

                # 提取 import 语句
                for match in re.finditer(r'^(?:from\s+(\S+)|import\s+(\S+))', content, re.MULTILINE):
                    module = match.group(1) or match.group(2)
                    if module:
                        # 转换为可能的文件路径
                        module_path = module.replace('.', '/') + '.py'
                        self._import_graph[relative_path].add(module_path)
            except Exception:
                pass

    def get_dependents(self, file_path: str) -> List[str]:
        """获取依赖于指定文件的所有文件"""
        if not self._import_graph:
            self.build_import_graph()

        dependents = []
        for file, imports in self._import_graph.items():
            if file_path in imports or any(file_path.endswith(imp) for imp in imports):
                dependents.append(file)

        return dependents


# =============================================================================
# 回归检测器
# =============================================================================
class RegressionDetector:
    """回归检测器 - 检查修复是否仍然有效"""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git = GitAnalyzer(repo_path)

    def check_code_exists(self, file_path: str, code_snippet: str) -> bool:
        """检查代码片段是否存在于文件中"""
        content = self.git.get_current_file_content(file_path)
        # 规范化空白字符进行比较
        normalized_content = ' '.join(content.split())
        normalized_snippet = ' '.join(code_snippet.split())
        return normalized_snippet in normalized_content

    def check_code_not_exists(self, file_path: str, code_snippet: str) -> bool:
        """检查代码片段不存在于文件中"""
        return not self.check_code_exists(file_path, code_snippet)

    def check_pattern_exists(self, file_path: str, pattern: str) -> bool:
        """检查正则模式是否匹配"""
        content = self.git.get_current_file_content(file_path)
        return bool(re.search(pattern, content))

    def generate_checks(self, analysis: CommitAnalysis) -> List[RegressionCheck]:
        """为提交生成回归检测"""
        checks = []

        # 只为 fix 类型的提交生成检测
        if analysis.commit_type != 'fix':
            return checks

        for change in analysis.code_changes:
            file_path = change.file_path

            # 检查关键添加的代码是否仍存在
            for key_addition in analysis.key_additions[:5]:  # 限制数量
                if len(key_addition) < 15:  # 太短的代码片段容易误报
                    continue

                exists = self.check_code_exists(file_path, key_addition)
                checks.append(RegressionCheck(
                    commit_hash=analysis.short_hash,
                    description=f"修复代码应存在: {key_addition[:50]}...",
                    check_type='code_exists',
                    file_path=file_path,
                    expected=key_addition[:100],
                    actual='存在' if exists else '不存在',
                    passed=exists,
                    severity=analysis.severity,
                ))

            # 检查被移除的问题代码是否回来了
            for key_removal in analysis.key_removals[:3]:
                if len(key_removal) < 20:
                    continue

                not_exists = self.check_code_not_exists(file_path, key_removal)
                if not not_exists:  # 问题代码回来了
                    checks.append(RegressionCheck(
                        commit_hash=analysis.short_hash,
                        description=f"问题代码不应存在: {key_removal[:50]}...",
                        check_type='code_removed',
                        file_path=file_path,
                        expected='不存在',
                        actual='存在 (可能是回归!)',
                        passed=not_exists,
                        severity='high',  # 问题代码回来是高严重性
                    ))

        return checks


# =============================================================================
# 连锁反应检测
# =============================================================================
class ChainReactionDetector:
    """检测修改可能导致的连锁反应"""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.dep_analyzer = DependencyAnalyzer(repo_path)

    def detect(self, changed_files: List[str]) -> List[Dict[str, Any]]:
        """检测连锁反应"""
        reactions = []

        self.dep_analyzer.build_import_graph()

        for file_path in changed_files:
            dependents = self.dep_analyzer.get_dependents(file_path)

            if dependents:
                reactions.append({
                    'changed_file': file_path,
                    'affected_files': dependents,
                    'risk': 'high' if len(dependents) > 5 else 'medium',
                    'suggestion': f"检查 {len(dependents)} 个依赖文件是否受影响",
                })

        return reactions


# =============================================================================
# 主分析器
# =============================================================================
class GitChangeAnalyzer:
    """Git 变更分析器 - 主类"""

    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path(__file__).parent
        self.git = GitAnalyzer(self.repo_path)
        self.regression_detector = RegressionDetector(self.repo_path)
        self.chain_detector = ChainReactionDetector(self.repo_path)

    def analyze_commit(self, commit: Dict[str, str]) -> CommitAnalysis:
        """分析单个提交"""
        commit_hash = commit['hash']

        # 获取 diff
        diff = self.git.get_commit_diff(commit_hash)
        files = self.git.get_commit_files(commit_hash)

        # 分析类型
        commit_type, severity, category = CommitTypeAnalyzer.analyze(
            commit['message'], diff
        )

        # 解析代码变更
        code_changes = DiffParser.parse(diff)

        # 提取关键代码
        all_additions = []
        all_removals = []
        for change in code_changes:
            all_additions.extend(change.added_lines)
            all_removals.extend(change.removed_lines)

        key_additions, key_removals = KeyCodeExtractor.extract_key_code(
            all_additions, all_removals
        )

        return CommitAnalysis(
            commit_hash=commit_hash,
            short_hash=commit['short_hash'],
            author=commit['author'],
            date=commit['date'],
            message=commit['message'],
            commit_type=commit_type,
            severity=severity,
            category=category,
            files_changed=files,
            code_changes=code_changes,
            key_additions=key_additions,
            key_removals=key_removals,
        )

    def analyze_all(self,
                   since: str = None,
                   limit: int = None,
                   verbose: bool = True) -> List[CommitAnalysis]:
        """分析所有提交"""
        commits = self.git.get_commits(since=since, limit=limit)

        if verbose:
            print_info(f"分析 {len(commits)} 个提交...")

        analyses = []
        for i, commit in enumerate(commits):
            if verbose and (i + 1) % 10 == 0:
                print_info(f"进度: {i + 1}/{len(commits)}")

            analysis = self.analyze_commit(commit)
            analyses.append(analysis)

        return analyses

    def run_regression_checks(self,
                             analyses: List[CommitAnalysis],
                             verbose: bool = True) -> List[RegressionCheck]:
        """运行回归检测"""
        all_checks = []

        # 只检查 fix 类型的提交
        fix_commits = [a for a in analyses if a.commit_type == 'fix']

        if verbose:
            print_info(f"检测 {len(fix_commits)} 个修复提交的回归...")

        for analysis in fix_commits:
            checks = self.regression_detector.generate_checks(analysis)
            all_checks.extend(checks)

        return all_checks

    def generate_report(self,
                       analyses: List[CommitAnalysis],
                       checks: List[RegressionCheck] = None,
                       verbose: bool = True) -> Dict[str, Any]:
        """生成分析报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_commits': len(analyses),
            'by_type': defaultdict(int),
            'by_severity': defaultdict(int),
            'by_category': defaultdict(int),
            'fix_commits': [],
            'potential_issues': [],
            'regression_checks': {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'failures': [],
            },
        }

        # 统计
        for analysis in analyses:
            report['by_type'][analysis.commit_type] += 1
            report['by_severity'][analysis.severity] += 1
            report['by_category'][analysis.category] += 1

            if analysis.commit_type == 'fix':
                report['fix_commits'].append({
                    'hash': analysis.short_hash,
                    'date': analysis.date,
                    'message': analysis.message[:80],
                    'severity': analysis.severity,
                    'category': analysis.category,
                    'files': analysis.files_changed,
                    'key_additions': analysis.key_additions[:5],
                })

        # 回归检测结果
        if checks:
            report['regression_checks']['total'] = len(checks)
            report['regression_checks']['passed'] = sum(1 for c in checks if c.passed)
            report['regression_checks']['failed'] = sum(1 for c in checks if not c.passed)
            report['regression_checks']['failures'] = [
                {
                    'commit': c.commit_hash,
                    'description': c.description,
                    'file': c.file_path,
                    'severity': c.severity,
                }
                for c in checks if not c.passed
            ]

        # 连锁反应
        all_changed_files = set()
        for analysis in analyses[:20]:  # 只检查最近的
            all_changed_files.update(analysis.files_changed)

        chain_reactions = self.chain_detector.detect(list(all_changed_files))
        report['chain_reactions'] = chain_reactions

        return report


# =============================================================================
# 主函数
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description='Git 变更自动分析器 - 从提交历史推断并验证修复'
    )
    parser.add_argument('--since', type=str, help='分析起始时间 (如 "1 week", "2024-01-01")')
    parser.add_argument('--commits', '-n', type=int, default=50, help='分析提交数量 (默认 50)')
    parser.add_argument('--check', action='store_true', help='运行回归检测')
    parser.add_argument('--report', action='store_true', help='生成详细报告')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    parser.add_argument('--fix-only', action='store_true', help='只显示 fix 类型提交')

    args = parser.parse_args()

    if not args.json:
        print_header("Git 变更自动分析器")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    analyzer = GitChangeAnalyzer()

    # 分析提交
    if not args.json:
        print_section("分析提交历史")

    analyses = analyzer.analyze_all(
        since=args.since,
        limit=args.commits,
        verbose=not args.json
    )

    # 运行回归检测
    checks = []
    if args.check:
        if not args.json:
            print_section("回归检测")
        checks = analyzer.run_regression_checks(analyses, verbose=not args.json)

    # 生成报告
    report = analyzer.generate_report(analyses, checks, verbose=not args.json)

    if args.json:
        # 转换 defaultdict 为普通 dict
        report['by_type'] = dict(report['by_type'])
        report['by_severity'] = dict(report['by_severity'])
        report['by_category'] = dict(report['by_category'])
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    # 打印报告
    print_section("提交统计")
    print_info(f"总提交数: {report['total_commits']}")

    print("\n  按类型:")
    for ctype, count in sorted(report['by_type'].items(), key=lambda x: -x[1]):
        icon = '🔧' if ctype == 'fix' else '✨' if ctype == 'feat' else '📝'
        print(f"    {icon} {ctype}: {count}")

    print("\n  按严重程度:")
    for sev, count in report['by_severity'].items():
        color = Colors.RED if sev == 'critical' else Colors.YELLOW if sev == 'high' else Colors.WHITE
        print(f"    {color}{sev}: {count}{Colors.RESET}")

    # 显示修复提交
    if args.fix_only or args.report:
        print_section(f"修复提交 ({len(report['fix_commits'])})")
        for fix in report['fix_commits'][:20]:
            severity_color = (Colors.RED if fix['severity'] == 'critical'
                            else Colors.YELLOW if fix['severity'] == 'high'
                            else Colors.WHITE)
            print(f"  {fix['hash']} [{severity_color}{fix['severity']}{Colors.RESET}] {fix['message'][:60]}")
            if fix['key_additions']:
                print(f"    关键添加: {fix['key_additions'][0][:50]}...")

    # 回归检测结果
    if args.check:
        print_section("回归检测结果")
        rc = report['regression_checks']

        if rc['total'] == 0:
            print_info("没有可检测的修复提交")
        else:
            passed_rate = rc['passed'] / rc['total'] * 100 if rc['total'] > 0 else 0

            if rc['failed'] == 0:
                print_ok(f"全部通过! {rc['passed']}/{rc['total']} ({passed_rate:.0f}%)")
            else:
                print_warn(f"通过: {rc['passed']}/{rc['total']} ({passed_rate:.0f}%)")
                print_error(f"失败: {rc['failed']}")

                for failure in rc['failures'][:10]:
                    print(f"    ❌ [{failure['severity']}] {failure['commit']}: {failure['description'][:50]}")

    # 连锁反应
    if report['chain_reactions']:
        print_section("潜在连锁反应")
        for reaction in report['chain_reactions'][:5]:
            risk_color = Colors.RED if reaction['risk'] == 'high' else Colors.YELLOW
            print(f"  {risk_color}[{reaction['risk']}]{Colors.RESET} {reaction['changed_file']}")
            print(f"    影响: {len(reaction['affected_files'])} 个文件")

    # 总结
    print_header("总结")

    issues_found = []
    if report['regression_checks'].get('failed', 0) > 0:
        issues_found.append(f"{report['regression_checks']['failed']} 个回归检测失败")
    if len(report['chain_reactions']) > 3:
        issues_found.append(f"{len(report['chain_reactions'])} 个潜在连锁反应")

    if issues_found:
        print_warn("发现潜在问题:")
        for issue in issues_found:
            print(f"  - {issue}")
    else:
        print_ok("未发现明显问题")

    print("\n建议:")
    print_info("1. 定期运行: python3 analyze_git_changes.py --check")
    print_info("2. PR 前检查: python3 analyze_git_changes.py --commits 10 --check")
    print_info("3. 详细报告: python3 analyze_git_changes.py --report --fix-only")


if __name__ == "__main__":
    main()
