#!/usr/bin/env python3
"""
Git Code Commit Statistics Tool
Count commits by programming language, categorized into frontend, backend, and others
"""

"""
像这样——你可以构造一个文档字符串
"""
# 不需要分号结尾
import subprocess
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path
from datetime import datetime, timedelta
import re
import calendar


class ProgressBar:
    """Progress bar utility class"""

    # ANSI color codes
    COLORS = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'purple': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'bold': '\033[1m',
        'reset': '\033[0m'
    }

    @staticmethod
    def create_bar(percentage: float, width: int = 30, fill_char: str = '█',
                   empty_char: str = '░', use_color: bool = True) -> str:
        """Create colored progress bar"""
        filled_length = int(width * percentage / 100)

        if use_color:
            # Choose color based on percentage
            if percentage >= 75:
                color = ProgressBar.COLORS['green']
            elif percentage >= 50:
                color = ProgressBar.COLORS['yellow']
            elif percentage >= 25:
                color = ProgressBar.COLORS['blue']
            else:
                color = ProgressBar.COLORS['cyan']

            filled_bar = color + fill_char * filled_length + ProgressBar.COLORS['reset']
            empty_bar = ProgressBar.COLORS['white'] + empty_char * (width - filled_length) + ProgressBar.COLORS['reset']
            bar = filled_bar + empty_bar
        else:
            bar = fill_char * filled_length + empty_char * (width - filled_length)

        return f"[{bar}] {percentage:5.1f}%"

    @staticmethod
    def format_language_stats(lang: str, additions: int, total_additions: int,
                              width: int = 25, use_color: bool = True) -> str:
        """Format language statistics information (without time display)"""
        percentage = (additions / total_additions * 100) if total_additions > 0 else 0
        bar = ProgressBar.create_bar(percentage, width, use_color=use_color)

        return f"  {lang:12} {bar} {additions:8,} lines"


class PersonalStatsAnalyzer:
    """Personal statistics analyzer"""

    def __init__(self):
        self.user_stats = defaultdict(lambda: {
            'additions': defaultdict(int),
            'deletions': defaultdict(int),
            'commits': defaultdict(int),
            'earliest_commit': {},
            'latest_commit': {},
            'repos': set()
        })

    def analyze_user_in_repo(self, repo_path: str, username: str) -> Dict:
        """Analyze user statistics in a specific repository"""
        try:
            # Get user's commit statistics (including detailed time)
            result = subprocess.run([
                'git', 'log', '--author', username, '--numstat',
                '--pretty=format:%ad|%ai|%s', '--date=short', '--all'
            ], cwd=repo_path, capture_output=True, text=True, check=True)

            if not result.stdout.strip():
                return None

            stats = {
                'additions': defaultdict(int),
                'deletions': defaultdict(int),
                'commits': defaultdict(int),
                'earliest_commit': {},
                'latest_commit': {},
                'earliest_commit_time': {},
                'latest_commit_time': {},
                'repo_name': os.path.basename(repo_path),
                'repo_path': repo_path
            }

            lines = result.stdout.strip().split('\n')
            current_date = None
            current_datetime = None
            current_message = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Parse date, detailed time and commit message
                if '|' in line and not line.split('\t')[0].isdigit():
                    parts = line.split('|')
                    if len(parts) >= 3:
                        current_date = parts[0]
                        current_datetime = parts[1]  # Complete time in ISO format
                        current_message = parts[2] if len(parts) > 2 else ""
                    elif len(parts) == 2:
                        current_date = parts[0]
                        current_datetime = parts[1]
                        current_message = ""
                    continue

                # Parse file change statistics
                parts = line.split('\t')
                if len(parts) == 3 and current_date:
                    try:
                        additions = int(parts[0]) if parts[0] != '-' else 0
                        deletions = int(parts[1]) if parts[1] != '-' else 0
                        filename = parts[2]

                        # Get language
                        language = self._get_file_language(filename)

                        # Skip excluded file types
                        if language is None:
                            continue

                        stats['additions'][language] += additions
                        stats['deletions'][language] += deletions
                        stats['commits'][language] += 1

                        # Update earliest and latest commit times
                        if language not in stats['earliest_commit'] or current_date < stats['earliest_commit'][
                            language]:
                            stats['earliest_commit'][language] = current_date
                            if current_datetime:
                                stats['earliest_commit_time'][language] = current_datetime

                        if language not in stats['latest_commit'] or current_date > stats['latest_commit'][language]:
                            stats['latest_commit'][language] = current_date
                            if current_datetime:
                                stats['latest_commit_time'][language] = current_datetime

                    except ValueError:
                        continue

            return stats if any(stats['additions'].values()) else None

        except subprocess.CalledProcessError:
            return None

    def _get_file_language(self, filename: str) -> str:
        """Simplified language identification"""
        analyzer = GitStatsAnalyzer()
        return analyzer.get_file_language(os.path.basename(filename))

    def analyze_user_across_system(self, username: str, max_workers: int = 4) -> Dict:
        """Analyze user commits across the entire system"""
        print(f"🔍 Searching for user '{username}' code commits...")

        # Scan Git repositories
        scanner = GitRepoScanner()
        repos = scanner.find_git_repos()
        repos = scanner.filter_repos(repos)

        if not repos:
            print("❌ No Git repositories found")
            return None

        # Parallel analysis
        user_data = {
            'username': username,
            'total_additions': defaultdict(int),
            'total_deletions': defaultdict(int),
            'total_commits': defaultdict(int),
            'earliest_commits': {},
            'latest_commits': {},
            'earliest_commit_times': {},
            'latest_commit_times': {},
            'repos_contributed': [],
            'repos_found': 0
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_repo = {
                executor.submit(self.analyze_user_in_repo, repo, username): repo
                for repo in repos
            }

            completed = 0
            for future in as_completed(future_to_repo):
                completed += 1
                repo_path = future_to_repo[future]
                result = future.result()

                if result:
                    user_data['repos_contributed'].append(result)

                    # Aggregate data
                    for lang, additions in result['additions'].items():
                        user_data['total_additions'][lang] += additions
                        user_data['total_deletions'][lang] += result['deletions'][lang]
                        user_data['total_commits'][lang] += result['commits'][lang]

                        # Update global earliest and latest times
                        if lang in result['earliest_commit']:
                            if (lang not in user_data['earliest_commits'] or
                                    result['earliest_commit'][lang] < user_data['earliest_commits'][lang]):
                                user_data['earliest_commits'][lang] = result['earliest_commit'][lang]
                                if lang in result.get('earliest_commit_time', {}):
                                    user_data['earliest_commit_times'][lang] = result['earliest_commit_time'][lang]

                        if lang in result['latest_commit']:
                            if (lang not in user_data['latest_commits'] or
                                    result['latest_commit'][lang] > user_data['latest_commits'][lang]):
                                user_data['latest_commits'][lang] = result['latest_commit'][lang]
                                if lang in result.get('latest_commit_time', {}):
                                    user_data['latest_commit_times'][lang] = result['latest_commit_time'][lang]

                if completed % 10 == 0:
                    print(f"📊 Analyzed {completed}/{len(repos)} repositories...")

        user_data['repos_found'] = len(repos)
        return user_data if user_data['repos_contributed'] else None

    def _parse_commit_time(self, iso_time: str) -> tuple:
        """Parse commit time, returns (hour, minute)"""
        try:
            # Handle various possible time formats
            if 'T' in iso_time:
                # ISO format: 2024-09-27T14:30:25+08:00
                time_part = iso_time.split('T')[1]
                if '+' in time_part:
                    time_part = time_part.split('+')[0]
                elif '-' in time_part and time_part.count('-') > 0:
                    time_part = time_part.split('-')[0]

                # Extract hour and minute
                time_components = time_part.split(':')
                if len(time_components) >= 2:
                    hour = int(time_components[0])
                    minute = int(time_components[1])
                    return (hour, minute)

            # Try parsing other formats
            dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
            return (dt.hour, dt.minute)
        except:
            return None

    def _collect_all_commit_times(self, user_data: Dict) -> list:
        """Collect all commit times from all repositories"""
        all_times = []

        for repo in user_data['repos_contributed']:
            for lang in repo.get('earliest_commit_time', {}):
                time_str = repo['earliest_commit_time'][lang]
                if time_str:
                    parsed_time = self._parse_commit_time(time_str)
                    if parsed_time:
                        all_times.append(parsed_time)

            for lang in repo.get('latest_commit_time', {}):
                time_str = repo['latest_commit_time'][lang]
                if time_str:
                    parsed_time = self._parse_commit_time(time_str)
                    if parsed_time:
                        all_times.append(parsed_time)

        return all_times

    def _find_earliest_latest_commit_times(self, user_data: Dict) -> tuple:
        """Find the earliest and latest time points (hour:minute) among all commits"""
        all_times = self._collect_all_commit_times(user_data)

        if not all_times:
            return None, None

        # Convert time to minutes for comparison
        def time_to_minutes(hour, minute):
            return hour * 60 + minute

        # Find earliest and latest times
        all_times_in_minutes = [(time_to_minutes(h, m), (h, m)) for h, m in all_times]
        all_times_in_minutes.sort()

        earliest = all_times_in_minutes[0][1]  # (hour, minute)
        latest = all_times_in_minutes[-1][1]  # (hour, minute)

        return earliest, latest

    def print_personal_stats(self, user_data: Dict, use_color: bool = True):
        """Print personal statistics information"""
        if not user_data:
            print("❌ No commit records found for this user")
            return

        username = user_data['username']
        total_additions = sum(user_data['total_additions'].values())
        total_deletions = sum(user_data['total_deletions'].values())
        repos_contributed = len(user_data['repos_contributed'])
        repos_found = user_data['repos_found']

        print("=" * 80)
        print(f"\033[1mPersonal code statistic report of {username}\033[0m")
        print("=" * 80)

        # Calculate overall time range
        all_earliest = []
        all_latest = []
        for earliest_time in user_data['earliest_commits'].values():
            if earliest_time:
                all_earliest.append(earliest_time)
        for latest_time in user_data['latest_commits'].values():
            if latest_time:
                all_latest.append(latest_time)

        overall_earliest = min(all_earliest) if all_earliest else "Unknown"
        overall_latest = max(all_latest) if all_latest else "Unknown"

        # Get earliest and latest detailed commit times
        earliest_time, latest_time = self._find_earliest_latest_commit_times(user_data)

        # Overview information
        print(f"\n\033[1m Overview:\033[0m")
        print(f"  Repositories contributed: {repos_contributed}/{repos_found}")
        print(
            f"  Total code lines: +{total_additions:,} -{total_deletions:,} (Net: {total_additions - total_deletions:+,})")

        # Display detailed commit times
        if earliest_time and latest_time:
            earliest_str = f"{earliest_time[0]:02d}:{earliest_time[1]:02d}"
            latest_str = f"{latest_time[0]:02d}:{latest_time[1]:02d}"
            print(f"  Commit times: {earliest_str} → {latest_str}")

        # Language statistics (sorted by lines)
        print(f"\n\033[1m Language Commit Statistics:\033[0m")
        language_items = sorted(user_data['total_additions'].items(),
                                key=lambda x: x[1], reverse=True)

        if not language_items:
            print("  No data")
            return

        for lang, additions in language_items:
            if additions == 0:
                continue

            stats_line = ProgressBar.format_language_stats(
                lang, additions, total_additions, use_color=use_color
            )
            print(stats_line)

        # Category statistics
        self._print_category_stats(user_data, total_additions, use_color)

        # Most active repositories
        print(f"\n\033[1m Most Active Repositories:\033[0m")
        repo_totals = []
        for repo in user_data['repos_contributed']:
            total = sum(repo['additions'].values())
            repo_totals.append((repo['repo_name'], total, repo['repo_path']))

        repo_totals.sort(key=lambda x: x[1], reverse=True)
        for i, (name, total, path) in enumerate(repo_totals[:10], 1):
            print(f"  {i:2d}. {name}: {total:,} lines")

    def _print_category_stats(self, user_data: Dict, total_additions: int, use_color: bool = True):
        """Print category statistics"""
        analyzer = GitStatsAnalyzer()

        frontend_total = 0
        backend_total = 0
        other_total = 0

        for lang, additions in user_data['total_additions'].items():
            category = analyzer.classify_language(lang)
            if category == 'frontend':
                frontend_total += additions
            elif category == 'backend':
                backend_total += additions
            else:
                other_total += additions

        print(f"\n\033[1m Technology Stack Distribution:\033[0m")
        if frontend_total > 0:
            bar = ProgressBar.create_bar(frontend_total / total_additions * 100, 20, use_color=use_color)
            print(f"  Front-End   {bar} {frontend_total:8,} lines")

        if backend_total > 0:
            bar = ProgressBar.create_bar(backend_total / total_additions * 100, 20, use_color=use_color)
            print(f"  Back-End    {bar} {backend_total:8,} lines")

        if other_total > 0:
            bar = ProgressBar.create_bar(other_total / total_additions * 100, 20, use_color=use_color)
            print(f"  Others      {bar} {other_total:8,} lines")

    def find_java_commits_by_user(self, username: str = "yancy.xiao") -> Dict:
        """Find earliest and latest Java commits by specific user"""
        print(f"🔍 Searching for Java commits by user '{username}'...")

        # Scan Git repositories
        scanner = GitRepoScanner()
        repos = scanner.find_git_repos()
        repos = scanner.filter_repos(repos)

        if not repos:
            print("❌ No Git repositories found")
            return None

        earliest_commit = None
        latest_commit = None

        for repo_path in repos:
            try:
                # Get Java commits by the user
                result = subprocess.run([
                    'git', 'log', '--author', username, '--grep', '\.java$',
                    '--pretty=format:%H|%ad|%ai|%s', '--date=short', '--all'
                ], cwd=repo_path, capture_output=True, text=True, check=True)

                if not result.stdout.strip():
                    continue

                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 4:
                            commit_hash = parts[0]
                            commit_date = parts[1]
                            commit_datetime = parts[2]
                            commit_message = parts[3]

                            # Check if this commit actually modified Java files
                            if self._has_java_changes(repo_path, commit_hash):
                                commit_info = {
                                    'hash': commit_hash,
                                    'date': commit_date,
                                    'datetime': commit_datetime,
                                    'message': commit_message,
                                    'repo': os.path.basename(repo_path)
                                }

                                # Update earliest commit
                                if earliest_commit is None or commit_date < earliest_commit['date']:
                                    earliest_commit = commit_info

                                # Update latest commit
                                if latest_commit is None or commit_date > latest_commit['date']:
                                    latest_commit = commit_info

            except subprocess.CalledProcessError:
                continue

        return {
            'earliest': earliest_commit,
            'latest': latest_commit
        }

    def _has_java_changes(self, repo_path: str, commit_hash: str) -> bool:
        """Check if a commit has Java file changes"""
        try:
            result = subprocess.run([
                'git', 'show', '--name-only', '--pretty=format:', commit_hash
            ], cwd=repo_path, capture_output=True, text=True, check=True)

            for line in result.stdout.strip().split('\n'):
                if line.strip().endswith('.java'):
                    return True
            return False
        except subprocess.CalledProcessError:
            return False

    def get_weekly_code_volume(self, username: str = "yancy.xiao") -> Dict:
        """Get weekly code volume for the last month"""
        print(f"📊 Analyzing weekly code volume for user '{username}'...")

        # Calculate date range (last month)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        # Scan Git repositories
        scanner = GitRepoScanner()
        repos = scanner.find_git_repos()
        repos = scanner.filter_repos(repos)

        if not repos:
            print("❌ No Git repositories found")
            return None

        # Initialize weekly data
        weekly_data = {}
        for i in range(4):  # 4 weeks
            week_start = start_date + timedelta(days=i * 7)
            week_end = min(week_start + timedelta(days=6), end_date)
            week_key = f"Week {i + 1} ({week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')})"
            weekly_data[week_key] = 0

        # If no commits in the last month, get the last 7 days from the most recent commit
        has_recent_commits = False

        for repo_path in repos:
            try:
                # Get commits in the date range
                result = subprocess.run([
                    'git', 'log', '--author', username, '--since', start_date.strftime('%Y-%m-%d'),
                    '--until', end_date.strftime('%Y-%m-%d'), '--numstat',
                    '--pretty=format:%ad|%ai', '--date=short', '--all'
                ], cwd=repo_path, capture_output=True, text=True, check=True)

                if result.stdout.strip():
                    has_recent_commits = True
                    self._process_weekly_commits(result.stdout, weekly_data, start_date)

            except subprocess.CalledProcessError:
                continue

        # If no recent commits, get the last 7 days from the most recent commit
        if not has_recent_commits:
            print("📅 No commits in the last month, analyzing last 7 days from most recent commit...")
            weekly_data = self._get_last_week_from_recent_commit(username, repos)

        return weekly_data

    def _process_weekly_commits(self, git_output: str, weekly_data: Dict, start_date: datetime):
        """Process git output to calculate weekly code volume"""
        lines = git_output.strip().split('\n')
        current_date = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse date line
            if '|' in line and not line.split('\t')[0].isdigit():
                current_date = line.split('|')[0]
                continue

            # Parse file change statistics
            parts = line.split('\t')
            if len(parts) == 3 and current_date:
                try:
                    additions = int(parts[0]) if parts[0] != '-' else 0
                    deletions = int(parts[1]) if parts[1] != '-' else 0
                    filename = parts[2]

                    # Only count code files (exclude common non-code files)
                    if self._is_code_file(filename):
                        commit_date = datetime.strptime(current_date, '%Y-%m-%d')
                        week_num = self._get_week_number(commit_date, start_date)

                        if 0 <= week_num < 4:
                            week_key = list(weekly_data.keys())[week_num]
                            weekly_data[week_key] += additions + deletions

                except ValueError:
                    continue

    def _is_code_file(self, filename: str) -> bool:
        """Check if file is a code file"""
        code_extensions = {'.py', '.java', '.js', '.ts', '.cpp', '.c', '.cs', '.php', '.rb', '.go', '.rs', '.swift',
                           '.kt', '.scala', '.clj', '.hs', '.ml', '.fs', '.vb', '.pas', '.d', '.nim', '.cr', '.zig'}
        excluded_files = {'package.json', 'package-lock.json', 'yarn.lock', 'requirements.txt', 'README.md', 'LICENSE'}

        if filename.lower() in excluded_files:
            return False

        if '.' in filename:
            ext = '.' + filename.split('.')[-1].lower()
            return ext in code_extensions

        return False

    def _get_week_number(self, commit_date: datetime, start_date: datetime) -> int:
        """Get week number (0-3) for a commit date"""
        days_diff = (commit_date - start_date).days
        return days_diff // 7

    def _get_last_week_from_recent_commit(self, username: str, repos: List[str]) -> Dict:
        """Get code volume for the last 7 days from the most recent commit"""
        # Find the most recent commit
        most_recent_date = None
        for repo_path in repos:
            try:
                result = subprocess.run([
                    'git', 'log', '--author', username, '--pretty=format:%ad', '--date=short', '--all', '-1'
                ], cwd=repo_path, capture_output=True, text=True, check=True)

                if result.stdout.strip():
                    commit_date = datetime.strptime(result.stdout.strip(), '%Y-%m-%d')
                    if most_recent_date is None or commit_date > most_recent_date:
                        most_recent_date = commit_date

            except subprocess.CalledProcessError:
                continue

        if most_recent_date is None:
            return {"No recent commits": 0}

        # Get commits from the last 7 days
        end_date = most_recent_date
        start_date = end_date - timedelta(days=6)

        weekly_data = {f"Last 7 days ({start_date.strftime('%m/%d')}-{end_date.strftime('%m/%d')})": 0}

        for repo_path in repos:
            try:
                result = subprocess.run([
                    'git', 'log', '--author', username, '--since', start_date.strftime('%Y-%m-%d'),
                    '--until', end_date.strftime('%Y-%m-%d'), '--numstat',
                    '--pretty=format:%ad|%ai', '--date=short', '--all'
                ], cwd=repo_path, capture_output=True, text=True, check=True)

                if result.stdout.strip():
                    self._process_weekly_commits(result.stdout, weekly_data, start_date)

            except subprocess.CalledProcessError:
                continue

        return weekly_data

    def print_java_commits_info(self, java_commits: Dict):
        """Print Java commits information"""
        if not java_commits or (not java_commits['earliest'] and not java_commits['latest']):
            print("❌ No Java commits found for yancy.xiao")
            return

        print("\n" + "=" * 80)
        print("\033[1mJava Commits by yancy.xiao\033[0m")
        print("=" * 80)

        if java_commits['earliest']:
            earliest = java_commits['earliest']
            print(f"\n\033[1mEarliest Java Commit:\033[0m")
            print(f"  Repository: {earliest['repo']}")
            print(f"  Date: {earliest['date']} ({earliest['datetime']})")
            print(f"  Hash: {earliest['hash']}")
            print(f"  Message: {earliest['message']}")

        if java_commits['latest']:
            latest = java_commits['latest']
            print(f"\n\033[1mLatest Java Commit:\033[0m")
            print(f"  Repository: {latest['repo']}")
            print(f"  Date: {latest['date']} ({latest['datetime']})")
            print(f"  Hash: {latest['hash']}")
            print(f"  Message: {latest['message']}")

    def print_weekly_code_volume(self, weekly_data: Dict):
        """Print weekly code volume with progress bars"""
        if not weekly_data:
            print("❌ No weekly code volume data available")
            return

        print("\n" + "=" * 80)
        print("\033[1mWeekly Code Volume (Last Month)\033[0m")
        print("=" * 80)

        # Find maximum value for scaling
        max_lines = max(weekly_data.values()) if weekly_data.values() else 1

        for week, lines in weekly_data.items():
            percentage = (lines / max_lines * 100) if max_lines > 0 else 0
            bar = ProgressBar.create_bar(percentage, 30, use_color=True)
            print(f"  {week:25} {bar} {lines:8,} lines")


def interactive_mode():
    """Interactive mode"""
    print("=" * 60)
    print("🚀 Git Personal Code Statistics Tool - Interactive Mode")
    print("=" * 60)
    print("✨ Enter your Git username to view personal code commit statistics")
    print("💡 Supports fuzzy matching, e.g.: 'john', 'john@example.com'")
    print("📝 Type 'exit' or 'quit' to exit")
    print()

    analyzer = PersonalStatsAnalyzer()

    while True:
        try:
            username = input("👤 Please enter Git username: ").strip()

            if not username:
                print("⚠️  Username cannot be empty, please try again")
                continue

            if username.lower() in ['exit', 'quit', 'q']:
                print("👋 Goodbye!")
                break

            # Analyze user statistics
            user_data = analyzer.analyze_user_across_system(username)

            if user_data:
                analyzer.print_personal_stats(user_data)

                # Ask whether to export
                while True:
                    export = input("\n💾 Export statistics to JSON file? (y/N): ").strip().lower()
                    if export in ['y', 'yes']:
                        filename = f"{username.replace('@', '_').replace(' ', '_')}_stats.json"
                        export_personal_stats(user_data, filename)
                        break
                    elif export in ['n', 'no', '']:
                        break
                    else:
                        print("Please enter y or n")
            else:
                print(f"❌ No commit records found for user '{username}'")
                print("💡 Please check if the username is correct, or if the user has commits in local Git repositories")

            print("\n" + "-" * 60)

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error occurred: {e}")


def export_personal_stats(user_data: Dict, filename: str):
    """Export personal statistics data"""
    try:
        # Convert defaultdict to regular dict for JSON serialization
        export_data = {
            'username': user_data['username'],
            'summary': {
                'total_additions': sum(user_data['total_additions'].values()),
                'total_deletions': sum(user_data['total_deletions'].values()),
                'repos_contributed': len(user_data['repos_contributed']),
                'repos_found': user_data['repos_found']
            },
            'languages': {
                lang: {
                    'additions': user_data['total_additions'][lang],
                    'deletions': user_data['total_deletions'][lang],
                    'commits': user_data['total_commits'][lang],
                    'earliest_commit': user_data['earliest_commits'].get(lang),
                    'latest_commit': user_data['latest_commits'].get(lang)
                }
                for lang in user_data['total_additions']
            },
            'repositories': [
                {
                    'name': repo['repo_name'],
                    'path': repo['repo_path'],
                    'total_additions': sum(repo['additions'].values()),
                    'languages': dict(repo['additions'])
                }
                for repo in user_data['repos_contributed']
            ]
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Statistics exported to: {filename}")

    except Exception as e:
        print(f"❌ Export failed: {e}")


class GitRepoScanner:
    """Git repository scanner"""

    def __init__(self):
        self.common_paths = [
            # User common directories
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Projects"),
            os.path.expanduser("~/Code"),
            os.path.expanduser("~/Development"),
            os.path.expanduser("~/Workspace"),
            os.path.expanduser("~/Git"),
            os.path.expanduser("~/src"),
            os.path.expanduser("~/work"),
            os.path.expanduser("~/coding"),
            os.path.expanduser("~/repos"),
            os.path.expanduser("~/github"),
            os.path.expanduser("~/gitlab"),

            # IDE workspace directories
            os.path.expanduser("~/PycharmProjects"),
            os.path.expanduser("~/WebstormProjects"),
            os.path.expanduser("~/IdeaProjects"),
            os.path.expanduser("~/AndroidStudioProjects"),
            os.path.expanduser("~/XcodeProjects"),
            os.path.expanduser("~/eclipse-workspace"),

            # Other user directories
            "/Users",
            "/opt",
            "/usr/local/src",
            "/usr/local/bin"
        ]

    def find_git_repos(self, search_paths: List[str] = None, max_depth: int = 5) -> List[str]:
        """Find Git repositories"""
        if search_paths is None:
            search_paths = self.common_paths

        repos = []
        seen_repos = set()

        print("🔍 Scanning Git repositories...")

        for base_path in search_paths:
            if not os.path.exists(base_path):
                continue

            try:
                # Use find command to quickly locate .git directories
                result = subprocess.run([
                    'find', base_path, '-type', 'd', '-name', '.git',
                    '-not', '-path', '*/.*/*',  # Exclude .git in hidden directories
                    '-maxdepth', str(max_depth)
                ], capture_output=True, text=True, timeout=30)

                for git_dir in result.stdout.strip().split('\n'):
                    if git_dir and git_dir.endswith('/.git'):
                        repo_path = os.path.dirname(git_dir)
                        real_path = os.path.realpath(repo_path)

                        if real_path not in seen_repos:
                            seen_repos.add(real_path)
                            repos.append(real_path)

            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                continue

        print(f"✅ Found {len(repos)} Git repositories")
        return sorted(repos)

    def filter_repos(self, repos: List[str], exclude_patterns: List[str] = None) -> List[str]:
        """Filter repositories"""
        if exclude_patterns is None:
            exclude_patterns = [
                '.Trash', 'node_modules', '.git', '__pycache__',
                '.venv', 'venv', '.DS_Store', 'Library', 'Applications'
            ]

        filtered = []
        for repo in repos:
            should_exclude = False
            for pattern in exclude_patterns:
                if pattern in repo:
                    should_exclude = True
                    break
            if not should_exclude:
                filtered.append(repo)

        return filtered


class SystemGitStatsAnalyzer:
    """System-level Git statistics analyzer"""

    def __init__(self):
        self.scanner = GitRepoScanner()
        self.repo_stats = {}  # Statistics results for each repository
        self.aggregated_stats = None  # Aggregated statistics results

    def analyze_repo(self, repo_path: str, args=None) -> Dict:
        """Analyze single repository"""
        try:
            analyzer = GitStatsAnalyzer(repo_path)
            if analyzer.is_git_repo():
                analyzer.analyze_commits(args)
                return {
                    'path': repo_path,
                    'name': os.path.basename(repo_path),
                    'success': True,
                    'analyzer': analyzer
                }
            else:
                return {'path': repo_path, 'success': False, 'error': 'Not a git repo'}
        except Exception as e:
            return {'path': repo_path, 'success': False, 'error': str(e)}

    def analyze_all_repos(self, args=None, max_workers: int = 4):
        """Analyze all repositories in parallel"""
        # Scan repositories
        repos = self.scanner.find_git_repos()
        if args and hasattr(args, 'exclude_patterns'):
            repos = self.scanner.filter_repos(repos, args.exclude_patterns)

        if not repos:
            print("❌ No Git repositories found")
            return

        print(f"📊 Starting analysis of {len(repos)} repositories...")

        # Parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks
            future_to_repo = {
                executor.submit(self.analyze_repo, repo, args): repo
                for repo in repos
            }

            # Collect results
            completed = 0
            for future in as_completed(future_to_repo):
                completed += 1
                result = future.result()

                if result['success']:
                    self.repo_stats[result['path']] = result
                    print(f"✅ [{completed}/{len(repos)}] {result['name']}")
                else:
                    if args and hasattr(args, 'verbose') and args.verbose:
                        print(f"❌ [{completed}/{len(repos)}] {result['path']}: {result.get('error', 'Unknown error')}")

        successful_repos = [r for r in self.repo_stats.values() if r['success']]
        print(f"\n🎉 Successfully analyzed {len(successful_repos)} repositories")

    def aggregate_stats(self):
        """Aggregate statistics from all repositories"""
        if not self.repo_stats:
            return

        # Create aggregated analyzer
        self.aggregated_stats = GitStatsAnalyzer()

        for repo_data in self.repo_stats.values():
            if not repo_data['success']:
                continue

            analyzer = repo_data['analyzer']

            # Aggregate language statistics
            for lang, additions in analyzer.language_additions.items():
                self.aggregated_stats.language_additions[lang] += additions
                self.aggregated_stats.language_deletions[lang] += analyzer.language_deletions[lang]
                self.aggregated_stats.language_commits[lang] += analyzer.language_commits[lang]

            # Aggregate frontend statistics
            for lang, additions in analyzer.frontend_additions.items():
                self.aggregated_stats.frontend_additions[lang] += additions
                self.aggregated_stats.frontend_deletions[lang] += analyzer.frontend_deletions[lang]
                self.aggregated_stats.frontend_commits[lang] += analyzer.frontend_commits[lang]

            # Aggregate backend statistics
            for lang, additions in analyzer.backend_additions.items():
                self.aggregated_stats.backend_additions[lang] += additions
                self.aggregated_stats.backend_deletions[lang] += analyzer.backend_deletions[lang]
                self.aggregated_stats.backend_commits[lang] += analyzer.backend_commits[lang]

            # Aggregate other statistics
            for lang, additions in analyzer.other_additions.items():
                self.aggregated_stats.other_additions[lang] += additions
                self.aggregated_stats.other_deletions[lang] += analyzer.other_deletions[lang]
                self.aggregated_stats.other_commits[lang] += analyzer.other_commits[lang]

    def print_system_stats(self, args=None):
        """Print system-level statistics results"""
        if not self.aggregated_stats:
            self.aggregate_stats()

        if not self.aggregated_stats:
            print("❌ No statistical data available")
            return

        print("=" * 80)
        print("\033[1mMac System Git Code Statistics Report\033[0m")
        print("=" * 80)

        # Repository overview
        successful_repos = len([r for r in self.repo_stats.values() if r['success']])
        print(f"\n\033[1mRepository Overview:\033[0m")
        print(f"  Total repositories: {successful_repos}")

        # Aggregated statistics
        self.aggregated_stats.print_stats(args)

        # Top repository statistics
        if args and not (args.frontend_only or args.backend_only):
            self.print_top_repos(args)

    def print_top_repos(self, args=None):
        """Print top repositories"""
        print(f"\n\033[1mMost Active Repositories (by total code lines):\033[0m")

        repo_totals = []
        for repo_data in self.repo_stats.values():
            if not repo_data['success']:
                continue

            analyzer = repo_data['analyzer']
            total_additions = sum(analyzer.language_additions.values())
            total_deletions = sum(analyzer.language_deletions.values())
            net_lines = total_additions - total_deletions

            repo_totals.append({
                'name': repo_data['name'],
                'path': repo_data['path'],
                'additions': total_additions,
                'deletions': total_deletions,
                'net': net_lines
            })

        # Sort by total additions
        repo_totals.sort(key=lambda x: x['additions'], reverse=True)

        top_limit = args.top if args and args.top > 0 else 15
        for i, repo in enumerate(repo_totals[:top_limit], 1):
            print(f"  {i:2d}. {repo['name']}: +{repo['additions']:,} -{repo['deletions']:,} (Net: {repo['net']:+,})")
            if args and hasattr(args, 'verbose') and args.verbose:
                print(f"      Path: {repo['path']}")


class GitStatsAnalyzer:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        # Count added and deleted lines
        self.language_additions = defaultdict(int)
        self.language_deletions = defaultdict(int)
        self.language_commits = defaultdict(int)

        self.frontend_additions = defaultdict(int)
        self.frontend_deletions = defaultdict(int)
        self.frontend_commits = defaultdict(int)

        self.backend_additions = defaultdict(int)
        self.backend_deletions = defaultdict(int)
        self.backend_commits = defaultdict(int)

        self.other_additions = defaultdict(int)
        self.other_deletions = defaultdict(int)
        self.other_commits = defaultdict(int)

        # File extension to language mapping (only includes real code files)
        self.extension_to_language = {
            # Frontend languages
            '.js': 'JavaScript',
            '.jsx': 'JavaScript',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript',
            '.vue': 'Vue',
            '.svelte': 'Svelte',
            '.dart': 'Dart',

            # Backend languages
            '.py': 'Python',
            '.java': 'Java',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.go': 'Go',
            '.rs': 'Rust',
            '.cpp': 'C++',
            '.cc': 'C++',
            '.cxx': 'C++',
            '.c': 'C',
            '.h': 'C/C++',
            '.hpp': 'C++',
            '.cs': 'C#',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.pl': 'Perl',
            '.swift': 'Swift',
            '.m': 'Objective-C',
            '.mm': 'Objective-C++',
            '.r': 'R',
            '.lua': 'Lua',
            '.jl': 'Julia',
            '.ex': 'Elixir',
            '.exs': 'Elixir',
            '.erl': 'Erlang',
            '.hrl': 'Erlang',
            '.clj': 'Clojure',
            '.cljs': 'ClojureScript',
            '.hs': 'Haskell',
            '.ml': 'OCaml',
            '.fs': 'F#',
            '.fsx': 'F#',
            '.vb': 'Visual Basic',
            '.pas': 'Pascal',
            '.d': 'D',
            '.nim': 'Nim',
            '.cr': 'Crystal',
            '.zig': 'Zig',

            # Database scripts
            '.sql': 'SQL',

            # Other code-related
            '.qml': 'QML',
        }

        # Frontend tech stack (excludes CSS and other style files)
        self.frontend_languages = {
            'JavaScript', 'TypeScript', 'Vue', 'Svelte', 'Dart', 'ClojureScript'
        }

        # Backend tech stack
        self.backend_languages = {
            'Python', 'Java', 'Kotlin', 'Scala', 'Go', 'Rust', 'C++', 'C',
            'C#', 'PHP', 'Ruby', 'Perl', 'Swift', 'Objective-C', 'Objective-C++',
            'R', 'Lua', 'Julia', 'Elixir', 'Erlang', 'Clojure', 'Haskell',
            'OCaml', 'F#', 'Visual Basic', 'Pascal', 'D', 'Nim', 'Crystal', 'Zig',
            'SQL'
        }

    def is_git_repo(self) -> bool:
        """Check if it's a git repository"""
        try:
            subprocess.run(['git', 'rev-parse', '--git-dir'],
                           cwd=self.repo_path,
                           capture_output=True,
                           check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def get_file_language(self, filename: str) -> str:
        """Get programming language based on filename"""
        # Excluded file types (not counted in statistics)
        excluded_extensions = {
            '.json', '.md', '.markdown', '.css', '.scss', '.sass', '.less', '.styl',
            '.html', '.htm', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            '.txt', '.rst', '.adoc', '.tex', '.gitignore', '.gitattributes',
            '.editorconfig', '.dockerignore', '.log', '.lock', '.svg', '.png',
            '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot',
            '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd'  # Exclude script files
        }

        # Excluded special filenames
        excluded_files = {
            'package.json', 'package-lock.json', 'yarn.lock', 'composer.lock',
            'Gemfile.lock', 'Pipfile.lock', 'poetry.lock', 'requirements.txt',
            'README.md', 'CHANGELOG.md', 'LICENSE', 'MANIFEST.in', '.babelrc',
            '.eslintrc', '.prettierrc', '.stylelintrc', 'tsconfig.json',
            'webpack.config.js', 'babel.config.js', 'jest.config.js',
            'rollup.config.js', 'vite.config.js', 'nuxt.config.js'
        }

        if filename.lower() in excluded_files:
            return None  # Return None to exclude

        # Check file extension
        if '.' in filename:
            ext = '.' + filename.split('.')[-1].lower()
            if ext in excluded_extensions:
                return None  # Return None to exclude

        # Handle preserved special filenames (real code files)
        special_files = {
            'Dockerfile': 'Dockerfile',
            'Makefile': 'Makefile',
            'makefile': 'Makefile',
            'CMakeLists.txt': 'CMake',
            'build.gradle': 'Gradle',
            'build.gradle.kts': 'Gradle',
            'pom.xml': 'Maven',
        }

        if filename in special_files:
            return special_files[filename]

        # Get file extension
        if '.' in filename:
            ext = '.' + filename.split('.')[-1].lower()
            language = self.extension_to_language.get(ext, 'Unknown')
            # Exclude Unknown types
            if language == 'Unknown':
                return None
            return language

        return None  # Also exclude files without extensions

    def classify_language(self, language: str) -> str:
        """Classify language as frontend, backend, or other"""
        if language in self.frontend_languages:
            return 'frontend'
        elif language in self.backend_languages:
            return 'backend'
        else:
            return 'other'

    def get_git_commit_stats(self, args=None) -> Dict[str, Dict[str, int]]:
        """Get git commit line statistics"""
        try:
            # Build git log command to get commit statistics
            cmd = ['git', 'log', '--numstat', '--pretty=format:']

            # Add author filter
            if args and args.author:
                cmd.extend(['--author', args.author])

            # Add date filter
            if args and args.since:
                cmd.extend(['--since', args.since])

            if args and args.until:
                cmd.extend(['--until', args.until])

            # Get all branches by default
            cmd.append('--all')

            result = subprocess.run(cmd, cwd=self.repo_path,
                                    capture_output=True, text=True, check=True)

            file_stats = {}
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if not line or line.startswith('commit'):
                    continue

                # Parse numstat output format: additions deletions filename
                parts = line.split('\t')
                if len(parts) == 3:
                    try:
                        additions = int(parts[0]) if parts[0] != '-' else 0
                        deletions = int(parts[1]) if parts[1] != '-' else 0
                        filename = parts[2]

                        if filename not in file_stats:
                            file_stats[filename] = {'additions': 0, 'deletions': 0}

                        file_stats[filename]['additions'] += additions
                        file_stats[filename]['deletions'] += deletions
                    except ValueError:
                        continue

            return file_stats
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to get git commit statistics: {e}")
            return {}

    def analyze_commits(self, args=None):
        """Analyze commit data"""
        file_stats = self.get_git_commit_stats(args)

        for file_path, stats in file_stats.items():
            if not file_path:
                continue

            # Get filename
            filename = os.path.basename(file_path)

            # Get language
            language = self.get_file_language(filename)

            # Skip excluded file types
            if language is None:
                continue

            additions = stats['additions']
            deletions = stats['deletions']

            # Count by language
            self.language_additions[language] += additions
            self.language_deletions[language] += deletions
            self.language_commits[language] += 1

            # Categorized statistics
            category = self.classify_language(language)
            if category == 'frontend':
                self.frontend_additions[language] += additions
                self.frontend_deletions[language] += deletions
                self.frontend_commits[language] += 1
            elif category == 'backend':
                self.backend_additions[language] += additions
                self.backend_deletions[language] += deletions
                self.backend_commits[language] += 1
            else:
                self.other_additions[language] += additions
                self.other_deletions[language] += deletions
                self.other_commits[language] += 1

    def print_stats(self, args=None):
        """Print statistics results"""

        # Get icon function
        def get_icons():
            if args and args.no_color:
                return {'frontend': '[F]', 'backend': '[B]', 'other': '[O]'}
            return {'frontend': '🎨', 'backend': '⚙️', 'other': '📁'}

        icons = get_icons()

        print("=" * 70)
        print("\033[1mGit Code Commit Statistics Report\033[0m")
        print("=" * 70)

        # Overall statistics
        total_additions = sum(self.language_additions.values())
        total_deletions = sum(self.language_deletions.values())
        total_files = sum(self.language_commits.values())

        if total_files == 0:
            print("⚠️  No commit records found")
            return

        print(f"\n\033[1mSummary:\033[0m")
        print(f"  Files: {total_files}")
        print(f"  Lines added: +{total_additions:,}")
        print(f"  Lines deleted: -{total_deletions:,}")
        print(f"  Net growth: {total_additions - total_deletions:,} lines")

        # Decide what to display based on parameters
        show_frontend = not (args and args.backend_only)
        show_backend = not (args and args.frontend_only)
        show_other = not (args and (args.frontend_only or args.backend_only))

        # Frontend statistics
        frontend_additions = sum(self.frontend_additions.values())
        frontend_deletions = sum(self.frontend_deletions.values())
        if show_frontend and frontend_additions > 0:
            print(f"\n\033[1m{icons['frontend']} Frontend:\033[0m")
            items = []
            for lang in self.frontend_additions:
                additions = self.frontend_additions[lang]
                deletions = self.frontend_deletions[lang]
                net = additions - deletions
                items.append((lang, additions, deletions, net))

            items.sort(key=lambda x: x[1], reverse=True)  # Sort by lines added
            if args and args.top > 0:
                items = items[:args.top]

            for lang, additions, deletions, net in items:
                print(f"  {lang}: +{additions:,} -{deletions:,} (Net: {net:+,})")

        # Backend statistics
        backend_additions = sum(self.backend_additions.values())
        backend_deletions = sum(self.backend_deletions.values())
        if show_backend and backend_additions > 0:
            print(f"\n\033[1m{icons['backend']} Backend:\033[0m")
            items = []
            for lang in self.backend_additions:
                additions = self.backend_additions[lang]
                deletions = self.backend_deletions[lang]
                net = additions - deletions
                items.append((lang, additions, deletions, net))

            items.sort(key=lambda x: x[1], reverse=True)
            if args and args.top > 0:
                items = items[:args.top]

            for lang, additions, deletions, net in items:
                print(f"  {lang}: +{additions:,} -{deletions:,} (Net: {net:+,})")

        # Other statistics
        other_additions = sum(self.other_additions.values())
        other_deletions = sum(self.other_deletions.values())
        if show_other and other_additions > 0:
            print(f"\n\033[1m{icons['other']} Others:\033[0m")
            items = []
            for lang in self.other_additions:
                additions = self.other_additions[lang]
                deletions = self.other_deletions[lang]
                net = additions - deletions
                items.append((lang, additions, deletions, net))

            items.sort(key=lambda x: x[1], reverse=True)
            if args and args.top > 0:
                items = items[:args.top]

            for lang, additions, deletions, net in items:
                print(f"  {lang}: +{additions:,} -{deletions:,} (Net: {net:+,})")

        # Language leaderboard
        if not (args and (args.frontend_only or args.backend_only)):
            print(f"\n\033[1mTop Language Leaderboard (by lines added):\033[0m")
            items = []
            for lang in self.language_additions:
                additions = self.language_additions[lang]
                deletions = self.language_deletions[lang]
                net = additions - deletions
                category = self.classify_language(lang)
                items.append((lang, additions, deletions, net, category))

            items.sort(key=lambda x: x[1], reverse=True)
            top_limit = args.top if args and args.top > 0 else 10

            for lang, additions, deletions, net, category in items[:top_limit]:
                category_icon = icons[category]
                percentage = (additions / total_additions * 100) if total_additions > 0 else 0
                print(f"  {category_icon} {lang}: +{additions:,} -{deletions:,} (Net: {net:+,}) {percentage:.1f}%")

    def export_json(self, output_file: str):
        """Export to JSON format"""
        # Build frontend data
        frontend_data = {}
        for lang in self.frontend_additions:
            frontend_data[lang] = {
                'additions': self.frontend_additions[lang],
                'deletions': self.frontend_deletions[lang],
                'net': self.frontend_additions[lang] - self.frontend_deletions[lang],
                'files': self.frontend_commits[lang]
            }

        # Build backend data
        backend_data = {}
        for lang in self.backend_additions:
            backend_data[lang] = {
                'additions': self.backend_additions[lang],
                'deletions': self.backend_deletions[lang],
                'net': self.backend_additions[lang] - self.backend_deletions[lang],
                'files': self.backend_commits[lang]
            }

        # Build other data
        other_data = {}
        for lang in self.other_additions:
            other_data[lang] = {
                'additions': self.other_additions[lang],
                'deletions': self.other_deletions[lang],
                'net': self.other_additions[lang] - self.other_deletions[lang],
                'files': self.other_commits[lang]
            }

        # Build overall data
        languages_data = {}
        for lang in self.language_additions:
            languages_data[lang] = {
                'additions': self.language_additions[lang],
                'deletions': self.language_deletions[lang],
                'net': self.language_additions[lang] - self.language_deletions[lang],
                'files': self.language_commits[lang],
                'category': self.classify_language(lang)
            }

        data = {
            'summary': {
                'total_files': sum(self.language_commits.values()),
                'total_additions': sum(self.language_additions.values()),
                'total_deletions': sum(self.language_deletions.values()),
                'net_lines': sum(self.language_additions.values()) - sum(self.language_deletions.values())
            },
            'frontend': frontend_data,
            'backend': backend_data,
            'other': other_data,
            'languages': languages_data
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n📄 Statistics exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Git Code Commit Statistics Tool - Supports system scanning and personal statistics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  %(prog)s                          # Analyze current directory
  %(prog)s -p /path/to/repo         # Analyze specified repository
  %(prog)s --system                 # Scan entire Mac system for Git repositories
  %(prog)s --system --top 10        # System scan, show top 10 languages
  %(prog)s --interactive            # Interactive personal statistics mode
  %(prog)s --personal "username"    # Personal statistics mode
  %(prog)s -o stats.json            # Export to JSON format
  %(prog)s --author "John Doe"      # Only count specified author's commits
  %(prog)s --since "2023-01-01"     # Count commits after specified date
        """)

    parser.add_argument('--path', '-p', default='.',
                        help='Git repository path (default: current directory)')
    parser.add_argument('--system', action='store_true',
                        help='Scan entire Mac system for Git repositories')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Launch interactive personal statistics mode')
    parser.add_argument('--personal',
                        help='Personal statistics mode, specify Git username')
    parser.add_argument('--output', '-o',
                        help='Export JSON file path')
    parser.add_argument('--author', '-a',
                        help='Only count commits from specified author')
    parser.add_argument('--since', '-s',
                        help='Count commits after specified date (format: YYYY-MM-DD)')
    parser.add_argument('--until', '-u',
                        help='Count commits before specified date (format: YYYY-MM-DD)')
    parser.add_argument('--top', '-t', type=int, default=0,
                        help='Show only top N languages/repositories (0 means show all)')
    parser.add_argument('--frontend-only', action='store_true',
                        help='Show only frontend statistics')
    parser.add_argument('--backend-only', action='store_true',
                        help='Show only backend statistics')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed information')
    parser.add_argument('--max-workers', type=int, default=4,
                        help='Maximum number of threads for parallel processing (default: 4)')

    args = parser.parse_args()

    # Interactive personal statistics mode
    if args.interactive:
        interactive_mode()
        return

    # Personal statistics mode
    if args.personal:
        analyzer = PersonalStatsAnalyzer()
        user_data = analyzer.analyze_user_across_system(args.personal, args.max_workers)

        if user_data:
            use_color = not args.no_color
            analyzer.print_personal_stats(user_data, use_color=use_color)

            # Add new features for yancy.xiao user
            if args.personal == "yancy.xiao":
                # Find Java commits
                java_commits = analyzer.find_java_commits_by_user("yancy.xiao")
                analyzer.print_java_commits_info(java_commits)

                # Get weekly code volume
                weekly_data = analyzer.get_weekly_code_volume("yancy.xiao")
                analyzer.print_weekly_code_volume(weekly_data)

            if args.output:
                export_personal_stats(user_data, args.output)
        else:
            print(f"❌ No commit records found for user '{args.personal}'")
        return

    # System-level scanning mode
    if args.system:
        system_analyzer = SystemGitStatsAnalyzer()
        system_analyzer.analyze_all_repos(args, max_workers=args.max_workers)
        system_analyzer.print_system_stats(args)

        if args.output:
            # Export aggregated statistics
            if system_analyzer.aggregated_stats:
                system_analyzer.aggregated_stats.export_json(args.output)
    else:
        # Single repository analysis mode
        analyzer = GitStatsAnalyzer(args.path)

        if not analyzer.is_git_repo():
            print(f"❌ Error: {args.path} is not a Git repository")
            print("💡 Tips:")
            print("   - Use --system parameter to scan entire system for Git repositories")
            print("   - Use --interactive parameter to launch personal statistics mode")
            sys.exit(1)

        if args.verbose:
            print(f"📁 Analyzing Git repository: {os.path.abspath(args.path)}")

        analyzer.analyze_commits(args)
        analyzer.print_stats(args)

        if args.output:
            analyzer.export_json(args.output)


if __name__ == "__main__":
    main()