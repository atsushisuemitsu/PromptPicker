#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Picker - Markdown からプロンプトサンプルを抽出・選択するツール

機能:
- 複数の .md ファイルからプロンプトを抽出
- メニュー選択式でプロンプトを表示
- キーワード検索
- クリップボードへコピー
- ファイルへエクスポート
"""

import re
import os
import sys
import glob
import json
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime


@dataclass
class PromptSample:
    """プロンプトサンプルのデータモデル"""
    id: int
    title: str
    content: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    level: str = ""
    category: str = ""
    page: str = ""
    source_file: str = ""
    usage_count: int = 0
    last_used: str = ""

    def get_sort_key(self) -> str:
        """ソート用のキーを生成（タイトルの正規化）"""
        # 数字部分を抽出してゼロパディング
        match = re.search(r'^(\d+)', self.title)
        if match:
            return match.group(1).zfill(5)
        return self.title

    def summary(self, max_len: int = 60) -> str:
        """プロンプトの要約を返す"""
        text = self.content.replace('\n', ' ').strip()
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def full_display(self) -> str:
        """フル表示用の文字列を返す"""
        lines = [
            f"{'='*60}",
            f"【{self.id}】 {self.title}",
            f"{'='*60}",
        ]
        if self.category:
            lines.append(f"カテゴリ: {self.category}")
        if self.tags:
            lines.append(f"タグ: {', '.join(self.tags)}")
        if self.level:
            lines.append(f"レベル: {self.level}")
        if self.page:
            lines.append(f"ページ: {self.page}")
        if self.description:
            lines.append(f"説明: {self.description}")
        if self.source_file:
            lines.append(f"ソース: {Path(self.source_file).name}")
        lines.append(f"{'-'*60}")
        lines.append(self.content)
        lines.append(f"{'='*60}")
        return '\n'.join(lines)


class MarkdownPromptParser:
    """Markdownファイルからプロンプトを抽出するパーサー"""

    def __init__(self):
        self.prompts: List[PromptSample] = []
        self.current_id = 0
        self.current_category = ""
        self.current_chapter = ""

    def parse_file(self, filepath: str) -> List[PromptSample]:
        """ファイルを解析してプロンプトを抽出"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        prompts = []

        # 形式A: 見出し + メタ情報 + fenced code block
        prompts.extend(self._parse_format_a(content, filepath))

        # 形式B: テーブル形式（この書籍の形式）
        prompts.extend(self._parse_table_format(content, filepath))

        # 形式C: シンプルなcode block (```prompt または ```text)
        prompts.extend(self._parse_code_blocks(content, filepath))

        # 重複を除去（タイトルの番号 + 内容の類似性で判定）
        seen_titles = {}  # title_number -> prompt
        unique_prompts = []

        for p in prompts:
            # タイトルから番号を抽出
            title_match = re.search(r'^(\d+)', p.title)
            title_num = title_match.group(1) if title_match else None

            # 内容の正規化（比較用）
            normalized_content = re.sub(r'\s+', '', p.content)[:100]  # 先頭100文字で比較

            if title_num:
                # 同じ番号のプロンプトがすでにある場合
                if title_num in seen_titles:
                    existing = seen_titles[title_num]
                    # より長いプロンプトを採用
                    if len(p.content) > len(existing.content):
                        seen_titles[title_num] = p
                else:
                    seen_titles[title_num] = p
            else:
                # 番号がない場合は内容で重複チェック
                is_duplicate = any(
                    normalized_content in re.sub(r'\s+', '', existing.content)[:100]
                    for existing in unique_prompts
                )
                if not is_duplicate:
                    unique_prompts.append(p)

        # 番号付きプロンプトを番号順にソートして追加
        sorted_numbered = sorted(seen_titles.values(), key=lambda x: int(re.search(r'^(\d+)', x.title).group(1)))
        unique_prompts = sorted_numbered + unique_prompts

        return unique_prompts

    def _parse_format_a(self, content: str, filepath: str) -> List[PromptSample]:
        """形式A: 見出し + メタ情報 + fenced code blockを解析"""
        prompts = []

        # パターン: ## タイトル: XXX → メタデータ → ```prompt ... ```
        pattern = r'''
            ^\#\#\s*(?:タイトル[:：]\s*)?(.+?)\s*$  # 見出し（タイトル）
            ([\s\S]*?)                              # メタデータ部分
            ```(?:prompt|text)?\s*\n                # コードブロック開始
            ([\s\S]*?)                              # プロンプト本文
            ```                                     # コードブロック終了
        '''

        matches = re.finditer(pattern, content, re.MULTILINE | re.VERBOSE)

        for match in matches:
            title = match.group(1).strip()
            meta_section = match.group(2)
            prompt_content = match.group(3).strip()

            if not prompt_content:
                continue

            # メタデータを解析
            tags = self._extract_meta(meta_section, r'-\s*tags?[:：]\s*(.+)', split=True)
            level = self._extract_meta(meta_section, r'-\s*level[:：]\s*(.+)')
            description = self._extract_meta(meta_section, r'-\s*description[:：]\s*(.+)')

            self.current_id += 1
            prompts.append(PromptSample(
                id=self.current_id,
                title=title,
                content=prompt_content,
                description=description,
                tags=tags,
                level=level,
                source_file=filepath
            ))

        return prompts

    def _parse_table_format(self, content: str, filepath: str) -> List[PromptSample]:
        """テーブル形式のプロンプトを解析（この書籍の形式）"""
        prompts = []

        # 章の見出しを追跡
        chapter_pattern = r'^###?\s*(?:第\d+章|[\d]+部)?\s*[「『]?(.+?)[」』]?\s*$'
        chapters = {}
        for match in re.finditer(chapter_pattern, content, re.MULTILINE):
            chapters[match.start()] = match.group(1).strip()

        # テーブル行を解析: | 番号 | タイトル | プロンプト | ページ |
        # [bg:gray] や [bg:yellow] などのマーカーを除去
        table_pattern = r'\|\s*(?:\[bg:\w+\])?\s*\**(\d+)\**\s*\|\s*(?:\[bg:\w+\])?\s*\**([^|]+?)\**\s*\|\s*(?:\[bg:\w+\])?\s*(.+?)\s*\|\s*(?:\[bg:\w+\])?\s*(\d+)?\s*\|'

        for match in re.finditer(table_pattern, content):
            num = match.group(1).strip()
            title = match.group(2).strip()
            prompt_text = match.group(3).strip()
            page = match.group(4).strip() if match.group(4) else ""

            # フォーマットマーカーを除去
            title = re.sub(r'\[bg:\w+\]', '', title).strip()
            title = re.sub(r'\*+', '', title).strip()
            prompt_text = re.sub(r'\[bg:\w+\]', '', prompt_text).strip()

            # プロンプトが短すぎる場合はスキップ（説明行の可能性）
            if len(prompt_text) < 20:
                continue

            # ヘッダー行をスキップ
            if title in ['---', '|', ''] or prompt_text.startswith('---'):
                continue

            # 現在の章を特定
            current_chapter = ""
            match_pos = match.start()
            for pos, ch in sorted(chapters.items()):
                if pos < match_pos:
                    current_chapter = ch

            self.current_id += 1
            prompts.append(PromptSample(
                id=self.current_id,
                title=f"{num}. {title}" if num else title,
                content=prompt_text,
                category=current_chapter,
                page=page,
                source_file=filepath
            ))

        return prompts

    def _parse_code_blocks(self, content: str, filepath: str) -> List[PromptSample]:
        """シンプルなcode blockを解析"""
        prompts = []

        # すでに形式Aで処理されていないスタンドアロンのコードブロック
        pattern = r'```(?:prompt|text|markdown)?\s*\n([\s\S]*?)```'

        for match in re.finditer(pattern, content):
            prompt_text = match.group(1).strip()

            # 短すぎるものや、コード（プログラム）っぽいものはスキップ
            if len(prompt_text) < 30:
                continue
            if re.search(r'^\s*(def |class |import |from |function |const |let |var )', prompt_text, re.MULTILINE):
                continue

            # 前後のコンテキストからタイトルを推測
            start = max(0, match.start() - 200)
            context = content[start:match.start()]

            # 直前の見出しを探す
            title_match = re.search(r'^\#\#+\s*(.+?)\s*$', context, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else f"プロンプト {self.current_id + 1}"

            self.current_id += 1
            prompts.append(PromptSample(
                id=self.current_id,
                title=title,
                content=prompt_text,
                source_file=filepath
            ))

        return prompts

    def _extract_meta(self, text: str, pattern: str, split: bool = False) -> Any:
        """メタデータを抽出"""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if split:
                return [v.strip() for v in re.split(r'[,、\s]+', value) if v.strip()]
            return value
        return [] if split else ""


class ClipboardManager:
    """クリップボード操作を管理（Windows対応）"""

    @staticmethod
    def copy(text: str) -> bool:
        """テキストをクリップボードにコピー"""
        try:
            # Windows: clip コマンドを使用
            if sys.platform == 'win32':
                process = subprocess.Popen(
                    ['clip'],
                    stdin=subprocess.PIPE,
                    shell=True
                )
                process.communicate(text.encode('utf-16-le'))
                return True
            # macOS
            elif sys.platform == 'darwin':
                process = subprocess.Popen(
                    ['pbcopy'],
                    stdin=subprocess.PIPE
                )
                process.communicate(text.encode('utf-8'))
                return True
            # Linux (xclip)
            else:
                process = subprocess.Popen(
                    ['xclip', '-selection', 'clipboard'],
                    stdin=subprocess.PIPE
                )
                process.communicate(text.encode('utf-8'))
                return True
        except Exception as e:
            print(f"クリップボードへのコピーに失敗しました: {e}")
            return False


class UsageTracker:
    """使用履歴を追跡・保存するクラス"""

    def __init__(self, history_file: str = None):
        if history_file is None:
            # スクリプトと同じディレクトリに履歴ファイルを保存
            script_dir = Path(__file__).parent
            self.history_file = script_dir / ".prompt_history.json"
        else:
            self.history_file = Path(history_file)
        self.usage_data: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        """履歴ファイルを読み込み"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.usage_data = json.load(f)
        except Exception:
            self.usage_data = {}

    def _save(self):
        """履歴ファイルに保存"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.usage_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 保存に失敗しても続行

    def _get_key(self, prompt: PromptSample) -> str:
        """プロンプトの一意キーを生成"""
        # タイトルと内容の先頭でキーを生成
        content_hash = prompt.content[:50].replace('\n', ' ').strip()
        return f"{prompt.title}::{content_hash}"

    def record_usage(self, prompt: PromptSample):
        """使用を記録"""
        key = self._get_key(prompt)
        now = datetime.now().isoformat()

        if key not in self.usage_data:
            self.usage_data[key] = {"count": 0, "last_used": now, "title": prompt.title}

        self.usage_data[key]["count"] += 1
        self.usage_data[key]["last_used"] = now
        self._save()

    def get_usage(self, prompt: PromptSample) -> tuple:
        """使用回数と最終使用日時を取得"""
        key = self._get_key(prompt)
        if key in self.usage_data:
            return self.usage_data[key]["count"], self.usage_data[key]["last_used"]
        return 0, ""

    def apply_usage_to_prompts(self, prompts: List[PromptSample]):
        """プロンプトリストに使用履歴を適用"""
        for prompt in prompts:
            count, last_used = self.get_usage(prompt)
            prompt.usage_count = count
            prompt.last_used = last_used

    def sort_by_usage(self, prompts: List[PromptSample]) -> List[PromptSample]:
        """使用頻度順にソート（よく使うものが上）"""
        return sorted(prompts, key=lambda p: (-p.usage_count, p.get_sort_key()))


class PromptPickerUI:
    """インタラクティブなメニューUI"""

    def __init__(self, prompts: List[PromptSample], usage_tracker: UsageTracker = None):
        self.usage_tracker = usage_tracker or UsageTracker()
        self.usage_tracker.apply_usage_to_prompts(prompts)
        # デフォルトは使用頻度順
        self.prompts = self.usage_tracker.sort_by_usage(prompts)
        self.filtered_prompts = self.prompts.copy()
        self.current_filter = ""
        self.page_size = 15
        self.current_page = 0
        self.sort_mode = "usage"  # "usage" or "number"

    def clear_screen(self):
        """画面をクリア"""
        os.system('cls' if sys.platform == 'win32' else 'clear')

    def show_header(self):
        """ヘッダーを表示"""
        print("=" * 70)
        print("  Prompt Picker - プロンプトサンプル選択ツール")
        print("=" * 70)
        sort_str = "使用頻度順" if self.sort_mode == "usage" else "番号順"
        print(f"  総数: {len(self.prompts)} 件 | 表示中: {len(self.filtered_prompts)} 件 | 並び: {sort_str}")
        if self.current_filter:
            print(f"  フィルタ: 「{self.current_filter}」")
        print("-" * 70)

    def show_menu(self):
        """メニューを表示"""
        print("\n【操作コマンド】")
        print("  番号   : プロンプトを表示")
        print("  s 検索語: 検索 (例: s アイデア)")
        print("  c      : フィルタをクリア")
        print("  n / p  : 次ページ / 前ページ")
        print("  t      : 並び替え (使用頻度/番号)")
        print("  l      : カテゴリ一覧")
        print("  q      : 終了")
        print("-" * 70)

    def show_prompt_list(self):
        """プロンプト一覧を表示"""
        total_pages = (len(self.filtered_prompts) - 1) // self.page_size + 1 if self.filtered_prompts else 1
        start = self.current_page * self.page_size
        end = min(start + self.page_size, len(self.filtered_prompts))

        print(f"\n【プロンプト一覧】 ページ {self.current_page + 1}/{total_pages}")
        print("-" * 70)

        if not self.filtered_prompts:
            print("  該当するプロンプトがありません。")
            return

        for prompt in self.filtered_prompts[start:end]:
            category_str = f"[{prompt.category[:15]}]" if prompt.category else ""
            usage_str = f"({prompt.usage_count}回)" if prompt.usage_count > 0 else ""
            print(f"  {prompt.id:3d}. {prompt.title[:25]:<25} {usage_str} {category_str}")
            print(f"       {prompt.summary(55)}")

    def show_categories(self):
        """カテゴリ一覧を表示"""
        categories = {}
        for p in self.prompts:
            cat = p.category or "未分類"
            categories[cat] = categories.get(cat, 0) + 1

        print("\n【カテゴリ一覧】")
        print("-" * 70)
        for cat, count in sorted(categories.items()):
            print(f"  - {cat}: {count}件")
        print("\n※ 's カテゴリ名' で絞り込めます")

    def search(self, query: str):
        """プロンプトを検索"""
        query = query.lower()
        self.filtered_prompts = [
            p for p in self.prompts
            if query in p.title.lower()
            or query in p.content.lower()
            or query in p.description.lower()
            or query in p.category.lower()
            or any(query in tag.lower() for tag in p.tags)
        ]
        self.current_filter = query
        self.current_page = 0

    def clear_filter(self):
        """フィルタをクリア"""
        self.filtered_prompts = self.prompts.copy()
        self.current_filter = ""
        self.current_page = 0

    def toggle_sort(self):
        """ソート順を切り替え"""
        if self.sort_mode == "usage":
            self.sort_mode = "number"
            self.prompts.sort(key=lambda p: p.get_sort_key())
        else:
            self.sort_mode = "usage"
            self.prompts = self.usage_tracker.sort_by_usage(self.prompts)
        self.filtered_prompts = self.prompts.copy()
        self.current_page = 0

    def show_prompt_detail(self, prompt: PromptSample):
        """プロンプト詳細を表示して操作を受け付ける"""
        # 使用を記録
        self.usage_tracker.record_usage(prompt)
        prompt.usage_count += 1

        while True:
            self.clear_screen()
            print(prompt.full_display())
            print(f"\n使用回数: {prompt.usage_count} 回")
            print("\n【操作】")
            print("  c: クリップボードにコピー")
            print("  e: ファイルに書き出し")
            print("  b: 一覧に戻る")
            print("-" * 60)

            choice = input("選択 > ").strip().lower()

            if choice == 'c':
                if ClipboardManager.copy(prompt.content):
                    print("\n[OK] クリップボードにコピーしました！")
                    input("Enterで続行...")
            elif choice == 'e':
                self.export_prompt(prompt)
            elif choice == 'b' or choice == '':
                break

    def export_prompt(self, prompt: PromptSample):
        """プロンプトをファイルに書き出し"""
        default_name = re.sub(r'[^\w\-]', '_', prompt.title)[:30] + ".txt"
        filename = input(f"ファイル名 [{default_name}]: ").strip()
        if not filename:
            filename = default_name

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# {prompt.title}\n\n")
                if prompt.description:
                    f.write(f"説明: {prompt.description}\n\n")
                f.write(prompt.content)
            print(f"\n[OK] '{filename}' に書き出しました！")
        except Exception as e:
            print(f"\n[ERR] 書き出しに失敗しました: {e}")

        input("Enterで続行...")

    def run(self):
        """メインループを実行"""
        while True:
            self.clear_screen()
            self.show_header()
            self.show_prompt_list()
            self.show_menu()

            choice = input("\n選択 > ").strip()

            if not choice:
                continue

            # 終了
            if choice.lower() == 'q':
                print("\nご利用ありがとうございました！")
                break

            # 検索
            if choice.lower().startswith('s '):
                query = choice[2:].strip()
                if query:
                    self.search(query)
                continue

            # フィルタクリア
            if choice.lower() == 'c':
                self.clear_filter()
                continue

            # 次ページ
            if choice.lower() == 'n':
                max_page = (len(self.filtered_prompts) - 1) // self.page_size
                if self.current_page < max_page:
                    self.current_page += 1
                continue

            # 前ページ
            if choice.lower() == 'p':
                if self.current_page > 0:
                    self.current_page -= 1
                continue

            # ソート切り替え
            if choice.lower() == 't':
                self.toggle_sort()
                continue

            # カテゴリ一覧
            if choice.lower() == 'l':
                self.clear_screen()
                self.show_categories()
                input("\nEnterで続行...")
                continue

            # 番号でプロンプト選択
            try:
                num = int(choice)
                prompt = next((p for p in self.filtered_prompts if p.id == num), None)
                if prompt:
                    self.show_prompt_detail(prompt)
                else:
                    print(f"\n[!] ID {num} のプロンプトが見つかりません。")
                    input("Enterで続行...")
            except ValueError:
                print(f"\n[!] 無効な入力です: {choice}")
                input("Enterで続行...")


def safe_print(text: str):
    """Windows コンソールでも安全に出力"""
    try:
        print(text)
    except UnicodeEncodeError:
        # 絵文字などを除去して出力
        cleaned = text.encode('cp932', errors='replace').decode('cp932')
        print(cleaned)


def main():
    """メイン関数"""
    import argparse

    # Windows コンソールのエンコーディング対策
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(
        description='Markdown からプロンプトサンプルを抽出・選択するツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  python prompt_picker.py prompts.md
  python prompt_picker.py *.md
  python prompt_picker.py -d ./prompts/
        '''
    )
    parser.add_argument(
        'files',
        nargs='*',
        default=['*.md'],
        help='読み込むMarkdownファイル（ワイルドカード可）'
    )
    parser.add_argument(
        '-d', '--directory',
        help='Markdownファイルを探すディレクトリ'
    )
    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='プロンプト一覧を表示して終了'
    )

    args = parser.parse_args()

    # ファイルを収集
    md_files = []

    if args.directory:
        md_files.extend(glob.glob(os.path.join(args.directory, '**/*.md'), recursive=True))

    for pattern in args.files:
        md_files.extend(glob.glob(pattern))

    # 重複を除去
    md_files = list(set(md_files))

    if not md_files:
        print("エラー: Markdownファイルが見つかりません。")
        print("使用法: python prompt_picker.py <file.md> または python prompt_picker.py -d <directory>")
        sys.exit(1)

    safe_print(f"[*] {len(md_files)} 個のファイルを読み込み中...")

    # プロンプトを解析
    parser_obj = MarkdownPromptParser()
    all_prompts = []

    for filepath in md_files:
        try:
            prompts = parser_obj.parse_file(filepath)
            all_prompts.extend(prompts)
            safe_print(f"  [+] {Path(filepath).name}: {len(prompts)} 件のプロンプトを抽出")
        except Exception as e:
            safe_print(f"  [-] {Path(filepath).name}: 読み込みエラー - {e}")

    if not all_prompts:
        print("\nエラー: プロンプトが1件も見つかりませんでした。")
        sys.exit(1)

    # IDを振り直し
    for i, prompt in enumerate(all_prompts, 1):
        prompt.id = i

    safe_print(f"\n[OK] 合計 {len(all_prompts)} 件のプロンプトを読み込みました。\n")

    # リスト表示モード
    if args.list:
        for p in all_prompts:
            safe_print(f"{p.id:3d}. {p.title}")
        return

    # インタラクティブモード
    input("Enterキーでメニューを開始...")
    ui = PromptPickerUI(all_prompts)
    ui.run()


if __name__ == '__main__':
    main()
