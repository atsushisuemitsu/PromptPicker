# Prompt Picker

Markdownファイルからプロンプトサンプルを抽出し、メニュー選択式で取得できるツール。

## 機能

- 複数の .md ファイルからプロンプトを自動抽出
- インタラクティブなメニュー選択
- キーワード検索
- クリップボードへコピー（Windows/macOS/Linux対応）
- ファイルへエクスポート

## 対応フォーマット

### 形式A: 見出し + メタ情報 + コードブロック

```markdown
## タイトル: ログ解析プロンプト
- tags: log, c++
- level: detailed
- description: ログから原因を推定する

\`\`\`prompt
ここにプロンプト本文
\`\`\`
```

### 形式B: テーブル形式

```markdown
| 番号 | タイトル | プロンプト | ページ |
|------|----------|-----------|--------|
| 1 | 要約 | 以下を要約してください... | 10 |
```

## 使い方

### 基本的な使い方

```bash
# 単一ファイル
python prompt_picker.py prompts.md

# 複数ファイル（ワイルドカード）
python prompt_picker.py *.md

# ディレクトリ指定
python prompt_picker.py -d ./prompts/
```

### オプション

```bash
# プロンプト一覧を表示して終了
python prompt_picker.py --list prompts.md

# ヘルプ
python prompt_picker.py --help
```

### インタラクティブモードの操作

| コマンド | 説明 |
|----------|------|
| 番号 | 指定したプロンプトを表示 |
| s 検索語 | キーワードで検索（例: `s アイデア`） |
| c | フィルタをクリア |
| n / p | 次ページ / 前ページ |
| l | カテゴリ一覧を表示 |
| q | 終了 |

### プロンプト詳細画面の操作

| コマンド | 説明 |
|----------|------|
| c | クリップボードにコピー |
| e | ファイルに書き出し |
| b | 一覧に戻る |

## 動作環境

- Python 3.7以上
- 外部依存なし（標準ライブラリのみ）
- Windows / macOS / Linux 対応

## ファイル構成

```
GetPrompt/
├── prompt_picker.py    # メインスクリプト
├── README.md           # このファイル
└── sample_prompts.md   # サンプルプロンプト
```
