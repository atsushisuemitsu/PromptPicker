#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Picker GUI - グラフィカルなプロンプト選択ツール

機能:
- 章→プロンプト番号の階層選択
- 検索フィルタ
- よく使うプロンプト上位3つを表示
- クリップボードへコピー
"""

import re
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# 埋め込みプロンプトデータをインポート
from prompt_data import PROMPTS


@dataclass
class PromptSample:
    """プロンプトサンプルのデータモデル"""
    id: int
    title: str
    content: str
    page: str = ""
    usage_count: int = 0
    last_used: str = ""


class UsageTracker:
    """使用履歴を管理"""

    def __init__(self, history_file: str = ".prompt_history.json"):
        self.history_file = Path(history_file)
        self.history: Dict[str, Dict] = {}
        self.load_history()

    def load_history(self):
        """履歴を読み込み"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except:
                self.history = {}

    def save_history(self):
        """履歴を保存"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def record_usage(self, prompt: PromptSample):
        """使用を記録"""
        key = prompt.title
        if key not in self.history:
            self.history[key] = {"count": 0, "last_used": ""}
        self.history[key]["count"] += 1
        self.history[key]["last_used"] = datetime.now().isoformat()
        self.save_history()

    def apply_usage_to_prompts(self, prompts: List[PromptSample]):
        """プロンプトに使用履歴を適用"""
        for prompt in prompts:
            key = prompt.title
            if key in self.history:
                prompt.usage_count = self.history[key]["count"]
                prompt.last_used = self.history[key]["last_used"]

    def sort_by_usage(self, prompts: List[PromptSample]) -> List[PromptSample]:
        """使用頻度でソート"""
        return sorted(prompts, key=lambda p: (-p.usage_count, p.title))


# 章と技法番号のマッピング
CHAPTER_MAP = {
    "第1章 「AI特有の力」で考える": (1, 6),
    "第2章 「自由な発想」で考える": (7, 12),
    "第3章 「ロジカルな発想」で考える": (13, 17),
    "第4章 考えを「発展」させる": (18, 23),
    "第5章 考えを「具体的」にする": (24, 26),
    "第6章 考えを「検証」する": (27, 32),
    "第7章 アイデアの「伝え方」を考える": (33, 36),
    "第8章 アイデアの「実行策」を考える": (37, 38),
    "第9章 「課題」を分析してヒントを得る": (39, 43),
    "第10章 「悩み」を分析してヒントを得る": (44, 45),
    "第11章 「人」を分析してヒントを得る": (46, 53),
    "第12章 「未来」を予測してヒントを得る": (54, 56),
}


def get_prompt_number(prompt: PromptSample) -> Optional[int]:
    """プロンプトのタイトルから番号を抽出"""
    match = re.search(r'^(\d+)', prompt.title)
    return int(match.group(1)) if match else None


def get_chapter_for_prompt(prompt: PromptSample) -> Optional[str]:
    """プロンプトの所属章を取得"""
    num = get_prompt_number(prompt)
    if num is None:
        return None
    for chapter, (start, end) in CHAPTER_MAP.items():
        if start <= num <= end:
            return chapter
    return None


def load_prompts() -> List[PromptSample]:
    """埋め込みデータからプロンプトを読み込み"""
    prompts = []
    for data in PROMPTS:
        prompts.append(PromptSample(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            page=data.get("page", "")
        ))
    return prompts


class PromptPickerGUI:
    """GUIベースのプロンプト選択ツール（階層表示版）"""

    def __init__(self, prompts: List[PromptSample]):
        self.usage_tracker = UsageTracker()
        self.usage_tracker.apply_usage_to_prompts(prompts)
        self.all_prompts = prompts
        self.current_prompt: Optional[PromptSample] = None
        self.current_view = "chapters"  # "chapters", "prompts", "search"
        self.current_chapter: Optional[str] = None

        # ウィンドウ作成
        self.root = tk.Tk()
        self.root.title("Prompt Picker - AIを使って考えるための全技術")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)

        # スタイル設定
        self.setup_styles()

        # UI構築
        self.setup_ui()

        # 初期表示
        self.show_chapters()

    def setup_styles(self):
        """スタイルを設定"""
        style = ttk.Style()
        style.theme_use('clam')

        # Treeview のスタイル
        style.configure("Treeview",
                        font=('Yu Gothic UI', 11),
                        rowheight=32)
        style.configure("Treeview.Heading",
                        font=('Yu Gothic UI', 11, 'bold'))

        # ボタンのスタイル
        style.configure("TButton",
                        font=('Yu Gothic UI', 10),
                        padding=5)

        style.configure("Big.TButton",
                        font=('Yu Gothic UI', 12),
                        padding=10)

        # ラベルのスタイル
        style.configure("TLabel",
                        font=('Yu Gothic UI', 10))

        style.configure("Title.TLabel",
                        font=('Yu Gothic UI', 14, 'bold'))

        style.configure("Chapter.TLabel",
                        font=('Yu Gothic UI', 12, 'bold'))

    def setup_ui(self):
        """UIを構築"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === 上部：よく使うプロンプト ===
        freq_frame = ttk.LabelFrame(main_frame, text="よく使うプロンプト TOP 3", padding=10)
        freq_frame.pack(fill=tk.X, pady=(0, 10))

        self.freq_buttons_frame = ttk.Frame(freq_frame)
        self.freq_buttons_frame.pack(fill=tk.X)

        # TOP3ボタンを配置
        self.freq_buttons: List[ttk.Button] = []
        for i in range(3):
            btn = ttk.Button(self.freq_buttons_frame, text=f"#{i+1}",
                           command=lambda idx=i: self.on_freq_click(idx))
            btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
            self.freq_buttons.append(btn)

        # === 検索 ===
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="検索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_changed)
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=(5, 10))

        ttk.Button(search_frame, text="クリア", command=self.clear_search).pack(side=tk.LEFT)

        # ナビゲーション表示
        self.nav_label = ttk.Label(search_frame, text="", style="Chapter.TLabel")
        self.nav_label.pack(side=tk.RIGHT)

        # === 中央：リストと詳細（PanedWindow） ===
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左側：リスト表示
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        # 戻るボタン
        self.back_btn = ttk.Button(left_frame, text="← 章一覧に戻る",
                                   command=self.show_chapters, style="Big.TButton")
        self.back_btn.pack(fill=tk.X, pady=(0, 5))
        self.back_btn.pack_forget()  # 初期は非表示

        # Listbox（一覧）
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(list_frame, font=('Yu Gothic UI', 12),
                                  selectmode=tk.SINGLE, activestyle='dotbox')
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 選択イベント
        self.listbox.bind('<<ListboxSelect>>', self.on_select)
        self.listbox.bind('<Double-1>', self.on_double_click)
        self.listbox.bind('<Return>', self.on_enter)

        # 右側：詳細表示
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        # タイトル
        self.detail_title = ttk.Label(right_frame, text="章またはプロンプトを選択してください",
                                       style="Title.TLabel", wraplength=550)
        self.detail_title.pack(fill=tk.X, pady=(0, 5))

        # メタ情報
        self.detail_meta = ttk.Label(right_frame, text="", foreground="gray")
        self.detail_meta.pack(fill=tk.X, pady=(0, 10))

        # プロンプト内容
        content_frame = ttk.Frame(right_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        self.content_text = tk.Text(content_frame, wrap=tk.WORD, font=('Yu Gothic UI', 11),
                                     bg='#f8f8f8', padx=10, pady=10)
        content_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL,
                                        command=self.content_text.yview)
        self.content_text.configure(yscrollcommand=content_scroll.set)

        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # === 下部：ボタン ===
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        self.copy_btn = ttk.Button(button_frame, text="クリップボードにコピー",
                                    command=self.copy_to_clipboard, style="Big.TButton")
        self.copy_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.export_btn = ttk.Button(button_frame, text="ファイルに保存",
                                      command=self.export_to_file)
        self.export_btn.pack(side=tk.LEFT)

        ttk.Button(button_frame, text="終了", command=self.root.quit).pack(side=tk.RIGHT)

        # キーボードショートカット
        self.root.bind('<Control-c>', lambda e: self.copy_to_clipboard())
        self.root.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.root.bind('<Escape>', self.on_escape)
        self.root.bind('<BackSpace>', lambda e: self.go_back())

        # TOP3を更新
        self.update_frequent_prompts()

    def update_frequent_prompts(self):
        """よく使うプロンプトTOP3を更新"""
        sorted_prompts = self.usage_tracker.sort_by_usage(self.all_prompts)
        used_prompts = [p for p in sorted_prompts if p.usage_count > 0][:3]

        for i, btn in enumerate(self.freq_buttons):
            if i < len(used_prompts):
                p = used_prompts[i]
                btn.configure(text=f"{p.title[:30]}... ({p.usage_count}回)",
                            state=tk.NORMAL)
                btn.prompt = p
            else:
                btn.configure(text=f"(まだ使用履歴なし)", state=tk.DISABLED)
                btn.prompt = None

    def on_freq_click(self, idx: int):
        """TOP3ボタンクリック時"""
        btn = self.freq_buttons[idx]
        if hasattr(btn, 'prompt') and btn.prompt:
            self.show_prompt_detail(btn.prompt)
            self.current_prompt = btn.prompt

    def show_chapters(self):
        """章一覧を表示"""
        self.current_view = "chapters"
        self.current_chapter = None
        self.back_btn.pack_forget()
        self.nav_label.config(text="章を選択してください")

        self.listbox.delete(0, tk.END)
        for chapter in CHAPTER_MAP.keys():
            start, end = CHAPTER_MAP[chapter]
            count = end - start + 1
            self.listbox.insert(tk.END, f"{chapter} ({count}個)")

        self.detail_title.config(text="章を選択してください")
        self.detail_meta.config(text="全56技法")
        self.content_text.config(state=tk.NORMAL)
        self.content_text.delete('1.0', tk.END)
        self.content_text.insert('1.0', "左のリストから章を選んでください。\n\n"
                                         "ダブルクリックまたはEnterで章内のプロンプト一覧を表示します。\n\n"
                                         "検索ボックスにキーワードを入力して検索することもできます。")
        self.content_text.config(state=tk.DISABLED)

    def show_prompts_in_chapter(self, chapter: str):
        """選択した章のプロンプト一覧を表示"""
        self.current_view = "prompts"
        self.current_chapter = chapter
        self.back_btn.pack(fill=tk.X, pady=(0, 5))
        self.nav_label.config(text=chapter)

        start, end = CHAPTER_MAP[chapter]

        self.listbox.delete(0, tk.END)
        for prompt in self.all_prompts:
            num = get_prompt_number(prompt)
            if num and start <= num <= end:
                usage_str = f" [{prompt.usage_count}回]" if prompt.usage_count > 0 else ""
                self.listbox.insert(tk.END, f"{prompt.title}{usage_str}")

        self.detail_title.config(text=f"{chapter}")
        self.detail_meta.config(text=f"技法 {start}〜{end}")
        self.content_text.config(state=tk.NORMAL)
        self.content_text.delete('1.0', tk.END)
        self.content_text.insert('1.0', "プロンプトを選択してください。\n\n"
                                         "ダブルクリックまたはEnterでクリップボードにコピーします。")
        self.content_text.config(state=tk.DISABLED)

    def show_search_results(self, query: str):
        """検索結果を表示"""
        self.current_view = "search"
        self.current_chapter = None
        self.back_btn.pack(fill=tk.X, pady=(0, 5))
        self.nav_label.config(text=f"検索: {query}")

        query_lower = query.lower()
        self.listbox.delete(0, tk.END)

        matches = []
        for prompt in self.all_prompts:
            if (query_lower in prompt.title.lower() or
                query_lower in prompt.content.lower()):
                matches.append(prompt)

        for prompt in matches:
            usage_str = f" [{prompt.usage_count}回]" if prompt.usage_count > 0 else ""
            self.listbox.insert(tk.END, f"{prompt.title}{usage_str}")

        self.detail_title.config(text=f"検索結果: {len(matches)}件")
        self.detail_meta.config(text=f"検索キーワード: {query}")
        self.content_text.config(state=tk.NORMAL)
        self.content_text.delete('1.0', tk.END)
        if matches:
            self.content_text.insert('1.0', "検索結果からプロンプトを選択してください。")
        else:
            self.content_text.insert('1.0', "該当するプロンプトが見つかりませんでした。")
        self.content_text.config(state=tk.DISABLED)

    def on_search_changed(self, *args):
        """検索テキスト変更時"""
        query = self.search_var.get().strip()
        if len(query) >= 2:
            self.show_search_results(query)
        elif query == "":
            self.show_chapters()

    def clear_search(self):
        """検索をクリア"""
        self.search_var.set("")
        self.show_chapters()

    def on_select(self, event):
        """アイテム選択時"""
        selection = self.listbox.curselection()
        if not selection:
            return

        idx = selection[0]

        if self.current_view == "chapters":
            # 章を選択した場合
            chapter = list(CHAPTER_MAP.keys())[idx]
            start, end = CHAPTER_MAP[chapter]
            self.detail_title.config(text=chapter)
            self.detail_meta.config(text=f"技法 {start}〜{end} ({end-start+1}個)")
            self.content_text.config(state=tk.NORMAL)
            self.content_text.delete('1.0', tk.END)
            prompts_in_chapter = [p for p in self.all_prompts
                                  if get_prompt_number(p) and start <= get_prompt_number(p) <= end]
            content = f"{chapter}\n\n含まれる技法:\n"
            for p in prompts_in_chapter:
                content += f"  ・{p.title}\n"
            content += "\nダブルクリックまたはEnterで技法一覧を表示"
            self.content_text.insert('1.0', content)
            self.content_text.config(state=tk.DISABLED)
            self.current_prompt = None

        else:
            # プロンプト選択
            if self.current_view == "prompts" and self.current_chapter:
                start, end = CHAPTER_MAP[self.current_chapter]
                prompts_in_view = [p for p in self.all_prompts
                                   if get_prompt_number(p) and start <= get_prompt_number(p) <= end]
            else:  # search view
                query = self.search_var.get().lower()
                prompts_in_view = [p for p in self.all_prompts
                                   if query in p.title.lower() or query in p.content.lower()]

            if idx < len(prompts_in_view):
                prompt = prompts_in_view[idx]
                self.show_prompt_detail(prompt)
                self.current_prompt = prompt

    def on_double_click(self, event):
        """ダブルクリック時"""
        selection = self.listbox.curselection()
        if not selection:
            return

        if self.current_view == "chapters":
            idx = selection[0]
            chapter = list(CHAPTER_MAP.keys())[idx]
            self.show_prompts_in_chapter(chapter)
        else:
            self.copy_to_clipboard()

    def on_enter(self, event):
        """Enterキー押下時"""
        selection = self.listbox.curselection()
        if not selection:
            return

        if self.current_view == "chapters":
            idx = selection[0]
            chapter = list(CHAPTER_MAP.keys())[idx]
            self.show_prompts_in_chapter(chapter)
        else:
            self.copy_to_clipboard()

    def on_escape(self, event):
        """Escapeキー押下時"""
        if self.search_var.get():
            self.clear_search()
        elif self.current_view != "chapters":
            self.show_chapters()

    def go_back(self):
        """戻る"""
        if self.current_view != "chapters":
            self.clear_search()
            self.show_chapters()

    def show_prompt_detail(self, prompt: PromptSample):
        """プロンプト詳細を表示"""
        self.current_prompt = prompt

        # タイトル
        self.detail_title.config(text=prompt.title)

        # メタ情報
        meta_parts = []
        chapter = get_chapter_for_prompt(prompt)
        if chapter:
            meta_parts.append(f"章: {chapter.split(' ')[0]}")
        if prompt.usage_count > 0:
            meta_parts.append(f"使用回数: {prompt.usage_count}回")
        if prompt.page:
            meta_parts.append(f"ページ: {prompt.page}")
        self.detail_meta.config(text=" | ".join(meta_parts) if meta_parts else "")

        # 内容
        self.content_text.config(state=tk.NORMAL)
        self.content_text.delete('1.0', tk.END)
        self.content_text.insert('1.0', prompt.content)
        self.content_text.config(state=tk.DISABLED)

    def copy_to_clipboard(self):
        """クリップボードにコピー"""
        if not self.current_prompt:
            messagebox.showwarning("警告", "プロンプトを選択してください")
            return

        # 使用を記録
        self.usage_tracker.record_usage(self.current_prompt)
        self.current_prompt.usage_count += 1

        # クリップボードにコピー
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_prompt.content)

        # TOP3を更新
        self.update_frequent_prompts()

        # リスト表示を更新
        if self.current_view == "prompts" and self.current_chapter:
            self.show_prompts_in_chapter(self.current_chapter)
        elif self.current_view == "search":
            self.show_search_results(self.search_var.get())

        # 通知
        messagebox.showinfo("コピー完了", f"「{self.current_prompt.title}」をクリップボードにコピーしました")

    def export_to_file(self):
        """ファイルに保存"""
        if not self.current_prompt:
            messagebox.showwarning("警告", "プロンプトを選択してください")
            return

        default_name = re.sub(r'[^\w\-]', '_', self.current_prompt.title)[:30] + ".txt"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {self.current_prompt.title}\n\n")
                    f.write(self.current_prompt.content)
                messagebox.showinfo("保存完了", f"ファイルに保存しました:\n{filepath}")
            except Exception as e:
                messagebox.showerror("エラー", f"保存に失敗しました:\n{e}")

    def run(self):
        """アプリケーションを実行"""
        self.root.mainloop()


def main():
    """メイン関数"""
    # 埋め込みデータからプロンプトを読み込み
    prompts = load_prompts()

    if not prompts:
        messagebox.showerror("エラー", "プロンプトデータが見つかりませんでした")
        sys.exit(1)

    # GUI起動
    app = PromptPickerGUI(prompts)
    app.run()


if __name__ == '__main__':
    main()
