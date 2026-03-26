[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-8B5CF6?style=for-the-badge)](https://modelcontextprotocol.io/)
[![Anki](https://img.shields.io/badge/Anki-.apkg_Generator-236ad5?style=for-the-badge)](https://apps.ankiweb.net/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

# Anki MCP Server

**任意のデータから高品質な Anki デッキ (.apkg) を自動生成する MCP サーバー**

どんな教科・分野のデータでも、Claude に渡すだけで Anki デッキに変換できます。英語学習向けの TTS 音声付きカードにも対応。

---

## 特徴

- **5種類のカードタイプ** に対応（用途に応じて最適なカードを自動選択）
- **TTS 音声対応** -- iOS AnkiMobile / PC 版 Anki で英単語を自動読み上げ
- **語彙デッキ一括生成** -- 英単語リストを渡すだけで品詞・語源・例文付きカードを生成
- **穴埋め一括生成** -- 長文から重要語句を穴埋めにしたカードを量産
- **`/anki` スラッシュコマンド** -- Claude Code 上で 11 フェーズ・24 並列サブエージェントによる高品質デッキ生成パイプライン

---

## カードタイプ一覧

| タイプ | 説明 | 用途 |
|--------|------|------|
| `basic` | 表 → 裏 | 一般的な Q&A、定義の暗記 |
| `reversed` | 表 → 裏 & 裏 → 表 | 英単語（英→日・日→英の両方向） |
| `cloze` | 穴埋め (`{{c1::答え}}`) | 文脈の中でキーワードを覚える |
| `typing` | タイプ入力 | スペル練習、正確な用語の暗記 |
| `listening` | 音声のみ → 意味を答える | リスニング力強化（TTS 必須） |

すべてのカードタイプで **HTML** (`<b>`, `<i>`, `<br>`, `<table>` 等) が使えます。

---

## 処理フロー

```mermaid
graph LR
    A[入力データ] --> B[Claude が分析]
    B --> C[MCP ツール呼び出し]
    C --> D{カードタイプ判定}
    D --> E[basic / reversed]
    D --> F[cloze]
    D --> G[typing / listening]
    E --> H[genanki でデッキ生成]
    F --> H
    G --> H
    H --> I[.apkg ファイル出力]
    I --> J[Anki にインポート]
```

---

## `/anki` コマンドのパイプライン

Claude Code の `/anki` スラッシュコマンドを使うと、以下の 11 フェーズを自動実行します。

```mermaid
graph TD
    P1[Phase 1: 入力分析 & 設計<br>4 エージェント同時] --> P2[Phase 2: ディープリサーチ & カード生成<br>4 エージェント同時]
    P2 --> P3[Phase 3: 例文強化 & 補足追加<br>4 エージェント同時]
    P3 --> P4[Phase 4: 統合 & 正規化]
    P4 --> P5[Phase 5: 4 観点クロスチェック<br>4 エージェント同時]
    P5 --> P6[Phase 6: 修正 & 補完]
    P6 --> P7[Phase 7: 例文最終品質チェック<br>4 エージェント同時]
    P7 --> P8[Phase 8: 最終ファクトチェック<br>4 エージェント同時]
    P8 --> P9[Phase 9: 最終修正 & フリーズ]
    P9 --> P10[Phase 10: .apkg 生成]
    P10 --> P11[Phase 11: 最終レポート]

    style P1 fill:#4CAF50,color:#fff
    style P2 fill:#4CAF50,color:#fff
    style P3 fill:#4CAF50,color:#fff
    style P5 fill:#4CAF50,color:#fff
    style P7 fill:#4CAF50,color:#fff
    style P8 fill:#4CAF50,color:#fff
```

> 緑のフェーズは **4 エージェント並列実行**（計 24 サブエージェント使用）

---

## インストール

### 1. リポジトリをクローン

```bash
git clone https://github.com/cUDGk/anki-mcp.git
cd anki-mcp
```

### 2. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 3. Claude Code に MCP サーバーとして登録

`~/.claude/settings.json` (グローバル) または `.claude/settings.json` (プロジェクト) に以下を追加:

```json
{
  "mcpServers": {
    "anki-deck-generator": {
      "command": "python",
      "args": ["C:/Users/user/anki-mcp/server.py"],
      "env": {}
    }
  }
}
```

> **macOS / Linux の場合**: `args` のパスを適宜変更してください。

### 4. `/anki` スラッシュコマンドをセットアップ（任意）

```bash
cp commands/anki.md ~/.claude/commands/anki.md
```

これにより、Claude Code 上で `/anki TOEIC英単語 500語` のように使えるようになります。

---

## 使い方

### MCP ツールとして使う

Claude Code のチャット内で、以下のように自然言語で依頼するだけで MCP ツールが自動的に呼び出されます:

```
「TOEIC頻出英単語50語のAnkiデッキを作って。TTS音声付きで。」
```

```
「高校物理の力学の穴埋めカードを30枚作って」
```

### 利用可能な MCP ツール

| ツール | 説明 |
|--------|------|
| `generate_anki_deck` | カードデータから Anki デッキを生成 |
| `generate_vocab_deck` | 語彙リストから英単語デッキを一括生成 |
| `generate_cloze_from_text` | 穴埋めカードを一括生成 |
| `list_card_types` | カードタイプの一覧と使い方を表示 |
| `merge_anki_decks` | 複数デッキのマージ手順を案内 |

### `/anki` コマンドで使う

```
/anki TOEIC英単語 800点レベル 100語
```

11 フェーズの品質管理パイプラインにより、以下が自動で行われます:

- Web 検索による正確な定義・例文の取得
- 4 観点クロスチェック（ファクト・網羅性・一貫性・学習設計）
- 品詞・語源・例文の自動付与
- TTS 音声・リスニングカードの自動生成

---

## 出力例

生成されたデッキは `~/Desktop/` に `.apkg` ファイルとして保存されます。Anki で「ファイル → インポート」から読み込めます。

```
~/Desktop/TOEIC英単語.apkg
~/Desktop/高校物理_力学.apkg
```

---

## 技術スタック

| コンポーネント | 技術 |
|----------------|------|
| MCP サーバー | [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (Python) |
| デッキ生成 | [genanki](https://github.com/kerrickstaley/genanki) |
| TTS | Anki 内蔵 TTS エンジン (`{{tts en_US:Word}}`) |
| スラッシュコマンド | Claude Code Custom Commands |

---

## Attribution

このプロジェクトは以下のオープンソースプロジェクトの上に構築されています:

- **[genanki](https://github.com/kerrickstaley/genanki)** -- Python で Anki デッキをプログラム的に生成するライブラリ。Kerrick Staley 氏によるプロジェクト。
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)** -- Model Context Protocol の公式 Python 実装。Anthropic による [MCP 仕様](https://modelcontextprotocol.io/) に基づく。

---

## ライセンス

[MIT License](LICENSE) -- Copyright (c) 2026 cUDGk
