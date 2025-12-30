#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Picker GUI - グラフィカルなプロンプト選択ツール

機能:
- マウス/キーボードでプロンプトを選択
- 検索フィルタ
- クリップボードへコピー
- 使用頻度でソート
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
from typing import List, Dict, Any

# 既存のパーサーをインポート
from prompt_picker import MarkdownPromptParser, PromptSample, UsageTracker


class PromptPickerGUI:
    """GUIベースのプロンプト選択ツール"""

    def __init__(self, prompts: List[PromptSample]):
        self.usage_tracker = UsageTracker()
        self.usage_tracker.apply_usage_to_prompts(prompts)
        self.all_prompts = prompts
        self.filtered_prompts = prompts.copy()
        self.sort_mode = "usage"  # "usage" or "number"

        # ウィンドウ作成
        self.root = tk.Tk()
        self.root.title("Prompt Picker - プロンプト選択ツール")
        self.root.geometry("1000x700")
        self.root.minsize(800, 500)

        # スタイル設定
        self.setup_styles()

        # UI構築
        self.setup_ui()

        # 初期ソート
        self.sort_prompts()

        # プロンプト一覧を表示
        self.refresh_list()

    def setup_styles(self):
        """スタイルを設定"""
        style = ttk.Style()
        style.theme_use('clam')

        # Treeview のスタイル
        style.configure("Treeview",
                        font=('Yu Gothic UI', 10),
                        rowheight=28)
        style.configure("Treeview.Heading",
                        font=('Yu Gothic UI', 10, 'bold'))

        # ボタンのスタイル
        style.configure("TButton",
                        font=('Yu Gothic UI', 10),
                        padding=5)

        # ラベルのスタイル
        style.configure("TLabel",
                        font=('Yu Gothic UI', 10))

        style.configure("Title.TLabel",
                        font=('Yu Gothic UI', 12, 'bold'))

    def setup_ui(self):
        """UIを構築"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === 上部：検索・フィルタ ===
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        # 検索
        ttk.Label(top_frame, text="検索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_changed)
        search_entry = ttk.Entry(top_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=(5, 20))

        # ソート
        ttk.Label(top_frame, text="並び順:").pack(side=tk.LEFT)
        self.sort_var = tk.StringVar(value="usage")
        sort_combo = ttk.Combobox(top_frame, textvariable=self.sort_var,
                                   values=["usage", "number"], width=12, state="readonly")
        sort_combo.pack(side=tk.LEFT, padx=5)
        sort_combo.bind('<<ComboboxSelected>>', self.on_sort_changed)

        # 件数表示
        self.count_label = ttk.Label(top_frame, text="")
        self.count_label.pack(side=tk.RIGHT)

        # === 中央：リストと詳細（PanedWindow） ===
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左側：プロンプト一覧
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        # Treeview（一覧）
        columns = ('id', 'title', 'usage', 'category')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings', selectmode='browse')

        self.tree.heading('id', text='#', anchor='center')
        self.tree.heading('title', text='タイトル', anchor='w')
        self.tree.heading('usage', text='使用回数', anchor='center')
        self.tree.heading('category', text='カテゴリ', anchor='w')

        self.tree.column('id', width=40, minwidth=40, anchor='center')
        self.tree.column('title', width=250, minwidth=150, anchor='w')
        self.tree.column('usage', width=70, minwidth=60, anchor='center')
        self.tree.column('category', width=150, minwidth=100, anchor='w')

        # スクロールバー
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 選択イベント
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        self.tree.bind('<Double-1>', self.on_double_click)

        # 右側：詳細表示
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        # タイトル
        self.detail_title = ttk.Label(right_frame, text="プロンプトを選択してください",
                                       style="Title.TLabel", wraplength=500)
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

        self.copy_btn = ttk.Button(button_frame, text="📋 クリップボードにコピー",
                                    command=self.copy_to_clipboard)
        self.copy_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.export_btn = ttk.Button(button_frame, text="💾 ファイルに保存",
                                      command=self.export_to_file)
        self.export_btn.pack(side=tk.LEFT)

        ttk.Button(button_frame, text="終了", command=self.root.quit).pack(side=tk.RIGHT)

        # キーボードショートカット
        self.root.bind('<Control-c>', lambda e: self.copy_to_clipboard())
        self.root.bind('<Control-f>', lambda e: search_entry.focus())
        self.root.bind('<Escape>', lambda e: self.search_var.set(''))

    def refresh_list(self):
        """一覧を更新"""
        # 既存アイテムをクリア
        for item in self.tree.get_children():
            self.tree.delete(item)

        # フィルタリング
        query = self.search_var.get().lower()
        if query:
            self.filtered_prompts = [
                p for p in self.all_prompts
                if query in p.title.lower()
                or query in p.content.lower()
                or query in p.category.lower()
            ]
        else:
            self.filtered_prompts = self.all_prompts.copy()

        # ソート
        self.sort_prompts()

        # 一覧に追加
        for prompt in self.filtered_prompts:
            usage_str = f"{prompt.usage_count}回" if prompt.usage_count > 0 else "-"
            self.tree.insert('', tk.END, iid=str(prompt.id),
                            values=(prompt.id, prompt.title, usage_str, prompt.category or '-'))

        # 件数更新
        self.count_label.config(text=f"表示: {len(self.filtered_prompts)} / {len(self.all_prompts)} 件")

    def sort_prompts(self):
        """ソートを適用"""
        if self.sort_var.get() == "usage":
            self.filtered_prompts = self.usage_tracker.sort_by_usage(self.filtered_prompts)
        else:
            self.filtered_prompts.sort(key=lambda p: p.get_sort_key())

    def on_search_changed(self, *args):
        """検索テキスト変更時"""
        self.refresh_list()

    def on_sort_changed(self, event):
        """ソート変更時"""
        self.refresh_list()

    def on_select(self, event):
        """アイテム選択時"""
        selection = self.tree.selection()
        if not selection:
            return

        prompt_id = int(selection[0])
        prompt = next((p for p in self.all_prompts if p.id == prompt_id), None)

        if prompt:
            self.show_prompt_detail(prompt)

    def on_double_click(self, event):
        """ダブルクリック時：クリップボードにコピー"""
        self.copy_to_clipboard()

    def show_prompt_detail(self, prompt: PromptSample):
        """プロンプト詳細を表示"""
        self.current_prompt = prompt

        # タイトル
        self.detail_title.config(text=prompt.title)

        # メタ情報
        meta_parts = []
        if prompt.category:
            meta_parts.append(f"カテゴリ: {prompt.category}")
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
        if not hasattr(self, 'current_prompt') or not self.current_prompt:
            messagebox.showwarning("警告", "プロンプトを選択してください")
            return

        # 使用を記録
        self.usage_tracker.record_usage(self.current_prompt)
        self.current_prompt.usage_count += 1

        # クリップボードにコピー
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_prompt.content)

        # 一覧を更新（使用回数の表示更新）
        self.refresh_list()

        # 通知
        messagebox.showinfo("コピー完了", "プロンプトをクリップボードにコピーしました")

    def export_to_file(self):
        """ファイルに保存"""
        if not hasattr(self, 'current_prompt') or not self.current_prompt:
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
    import argparse

    parser = argparse.ArgumentParser(description='Prompt Picker GUI')
    parser.add_argument('files', nargs='*', default=['*.md'],
                        help='読み込むMarkdownファイル')
    parser.add_argument('-d', '--directory', help='Markdownファイルを探すディレクトリ')

    args = parser.parse_args()

    # ファイルを収集
    import glob
    md_files = []

    if args.directory:
        md_files.extend(glob.glob(os.path.join(args.directory, '**/*.md'), recursive=True))

    for pattern in args.files:
        md_files.extend(glob.glob(pattern))

    md_files = list(set(md_files))

    if not md_files:
        messagebox.showerror("エラー", "Markdownファイルが見つかりません")
        sys.exit(1)

    # パース
    parser_obj = MarkdownPromptParser()
    all_prompts = []

    for filepath in md_files:
        try:
            prompts = parser_obj.parse_file(filepath)
            all_prompts.extend(prompts)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")

    if not all_prompts:
        messagebox.showerror("エラー", "プロンプトが見つかりませんでした")
        sys.exit(1)

    # IDを振り直し
    for i, prompt in enumerate(all_prompts, 1):
        prompt.id = i

    # GUI起動
    app = PromptPickerGUI(all_prompts)
    app.run()


if __name__ == '__main__':
    main()
