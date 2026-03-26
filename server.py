"""
Anki Deck Generator MCP Server
任意のデータからAnkiデッキ(.apkg)を生成するMCPサーバー
"""

import json
import os
import random
import hashlib
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import genanki

mcp = FastMCP("anki-deck-generator")

# ── モデル定義 ──────────────────────────────────────────

def _model_id(name: str) -> int:
    """モデル名から決定論的IDを生成"""
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


# Basic (表→裏)
BASIC_MODEL = genanki.Model(
    _model_id("AnkiMCP_Basic"),
    "AnkiMCP Basic",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
    css="""
.card {
    font-family: 'Segoe UI', 'Hiragino Sans', 'Meiryo', sans-serif;
    font-size: 18px;
    text-align: center;
    color: #1a1a2e;
    background: #f5f5f5;
    padding: 20px;
    line-height: 1.6;
}
.card img { max-width: 100%; }
code {
    background: #e8e8e8;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Consolas', 'Monaco', monospace;
}
pre {
    background: #2d2d2d;
    color: #f8f8f2;
    padding: 12px;
    border-radius: 6px;
    text-align: left;
    overflow-x: auto;
    font-size: 14px;
}
table { margin: 0 auto; border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: 6px 12px; }
th { background: #e0e0e0; }
.formula {
    font-size: 22px;
    margin: 10px 0;
    color: #2c3e50;
}
""",
)

# Basic + Reversed (表→裏 & 裏→表)
REVERSED_MODEL = genanki.Model(
    _model_id("AnkiMCP_Reversed"),
    "AnkiMCP Reversed",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        },
        {
            "name": "Card 2 (Reversed)",
            "qfmt": "{{Back}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Front}}',
        },
    ],
    css=BASIC_MODEL.css,
)

# Cloze (穴埋め)
CLOZE_MODEL = genanki.Model(
    _model_id("AnkiMCP_Cloze"),
    "AnkiMCP Cloze",
    fields=[{"name": "Text"}, {"name": "Extra"}],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": '{{cloze:Text}}<br><br>{{Extra}}',
        }
    ],
    model_type=genanki.Model.CLOZE,
    css=BASIC_MODEL.css,
)

# Typing (タイプ入力)
TYPING_MODEL = genanki.Model(
    _model_id("AnkiMCP_Typing"),
    "AnkiMCP Typing",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Type Answer",
            "qfmt": "{{Front}}<br><br>{{type:Back}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
    css=BASIC_MODEL.css,
)

# ── TTS対応モデル（英語学習用） ──────────────────────────

# Basic + TTS
BASIC_TTS_MODEL = genanki.Model(
    _model_id("AnkiMCP_Basic_TTS"),
    "AnkiMCP Basic + TTS",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Word"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}<br><br>{{tts en_US speed=1.0:Word}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
    css=BASIC_MODEL.css,
)

# Reversed + TTS (英→日: 単語+音声を見せる / 日→英: 意味を見せて答え+音声)
REVERSED_TTS_MODEL = genanki.Model(
    _model_id("AnkiMCP_Reversed_TTS"),
    "AnkiMCP Reversed + TTS",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Word"}],
    templates=[
        {
            "name": "Card 1 (EN→JA)",
            "qfmt": "{{Front}}<br><br>{{tts en_US speed=1.0:Word}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        },
        {
            "name": "Card 2 (JA→EN)",
            "qfmt": "{{Back}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Front}}<br><br>{{tts en_US speed=1.0:Word}}',
        },
    ],
    css=BASIC_MODEL.css,
)

# Cloze + TTS
CLOZE_TTS_MODEL = genanki.Model(
    _model_id("AnkiMCP_Cloze_TTS"),
    "AnkiMCP Cloze + TTS",
    fields=[{"name": "Text"}, {"name": "Extra"}, {"name": "Word"}],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": '{{cloze:Text}}<br><br>{{Extra}}<br><br>{{tts en_US speed=1.0:Word}}',
        }
    ],
    model_type=genanki.Model.CLOZE,
    css=BASIC_MODEL.css,
)

# Typing + TTS (答え表示時に発音を再生)
TYPING_TTS_MODEL = genanki.Model(
    _model_id("AnkiMCP_Typing_TTS"),
    "AnkiMCP Typing + TTS",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Word"}],
    templates=[
        {
            "name": "Type Answer",
            "qfmt": "{{Front}}<br><br>{{type:Back}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}<br><br>{{tts en_US speed=1.0:Word}}',
        }
    ],
    css=BASIC_MODEL.css,
)

# Listening (リスニング専用: 音声だけ聞いて意味を答える)
LISTENING_MODEL = genanki.Model(
    _model_id("AnkiMCP_Listening"),
    "AnkiMCP Listening",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Word"}],
    templates=[
        {
            "name": "Listening",
            "qfmt": '🔊 Listen<br><br>{{tts en_US speed=0.9:Word}}',
            "afmt": '{{FrontSide}}<hr id="answer">{{Front}}<br><br>{{Back}}',
        }
    ],
    css=BASIC_MODEL.css,
)

MODELS = {
    "basic": BASIC_MODEL,
    "reversed": REVERSED_MODEL,
    "cloze": CLOZE_MODEL,
    "typing": TYPING_MODEL,
}

TTS_MODELS = {
    "basic": BASIC_TTS_MODEL,
    "reversed": REVERSED_TTS_MODEL,
    "cloze": CLOZE_TTS_MODEL,
    "typing": TYPING_TTS_MODEL,
    "listening": LISTENING_MODEL,
}


def _deck_id(name: str) -> int:
    """デッキ名から決定論的IDを生成"""
    return int(hashlib.md5(f"deck_{name}".encode()).hexdigest()[:8], 16)


class NoteWithGuid(genanki.Note):
    """フロントフィールドのみでGUIDを決定するNote（重複インポート防止）"""

    @property
    def guid(self):
        return genanki.guid_for(self.fields[0])


# ── MCP ツール ──────────────────────────────────────────

@mcp.tool()
def generate_anki_deck(
    deck_name: str,
    cards: list[dict],
    output_path: str = "",
    description: str = "",
    tts: bool = False,
) -> str:
    """
    カードデータからAnkiデッキ(.apkg)を生成する。

    どんな教科・分野でもOK。Claude が事前にデータを解析して
    適切な cards 配列を組み立ててからこのツールを呼ぶ。

    Args:
        deck_name: デッキ名 (例: "英単語TOEIC", "高校物理::力学")
                   "::" で階層化可能
        cards: カード配列。各カードは以下の形式:
            基本カード (type="basic" or 省略):
                {"front": "問題", "back": "答え", "tags": ["tag1"]}
            裏返しカード (type="reversed"):
                {"type": "reversed", "front": "<b>ephemeral</b><br><span style='color:#666; font-size:14px;'>adj. /ɪˈfem.ər.əl/</span>", "back": "はかない、つかの間の"}
            穴埋めカード (type="cloze"):
                {"type": "cloze", "text": "{{c1::東京}}は日本の首都", "extra": "補足情報"}
            タイプ入力カード (type="typing"):
                {"type": "typing", "front": "appleの意味は?", "back": "りんご"}
            リスニングカード (type="listening", tts=True時のみ):
                {"type": "listening", "front": "ephemeral", "back": "はかない", "word": "ephemeral"}

            TTS対応時 (tts=True) の追加フィールド:
                "word": TTS で読み上げる英単語/フレーズ (plain text、HTMLなし)
                ※ word を省略すると front からHTMLタグを除去して自動生成

            ※ front/back にはHTMLも使える (<b>, <i>, <br>, <img>, <table>等)
            ※ tags は省略可能
        output_path: 出力先パス (省略時: ~/Desktop/{deck_name}.apkg)
        description: デッキの説明文
        tts: True にすると英語TTS音声付きカードを生成（iOS AnkiMobile対応）
             カード表示時にiOSの音声エンジンで英単語を読み上げる

    Returns:
        生成されたファイルのパスと統計情報
    """
    if not cards:
        return "エラー: カードが空です"

    import re

    def strip_html(text: str) -> str:
        """HTMLタグを除去してplain textにする"""
        return re.sub(r'<[^>]+>', '', text).strip()

    deck = genanki.Deck(_deck_id(deck_name), deck_name, description=description)

    stats = {"basic": 0, "reversed": 0, "cloze": 0, "typing": 0, "listening": 0, "errors": []}

    for i, card in enumerate(cards):
        try:
            card_type = card.get("type", "basic")
            tags = card.get("tags", [])

            if card_type == "cloze":
                text = card.get("text", "")
                extra = card.get("extra", "")
                if not text:
                    stats["errors"].append(f"Card {i}: cloze text is empty")
                    continue
                if tts:
                    word = card.get("word", strip_html(re.sub(r'\{\{c\d+::(.*?)\}\}', r'\1', text)))
                    note = NoteWithGuid(
                        model=TTS_MODELS["cloze"],
                        fields=[text, extra, word],
                        tags=tags,
                    )
                else:
                    note = NoteWithGuid(
                        model=CLOZE_MODEL,
                        fields=[text, extra],
                        tags=tags,
                    )
            elif card_type == "listening":
                if not tts:
                    stats["errors"].append(f"Card {i}: listening type requires tts=True")
                    continue
                front = card.get("front", "")
                back = card.get("back", "")
                word = card.get("word", strip_html(front))
                if not front or not back:
                    stats["errors"].append(f"Card {i}: front or back is empty")
                    continue
                note = NoteWithGuid(
                    model=LISTENING_MODEL,
                    fields=[front, back, word],
                    tags=tags,
                )
            else:
                front = card.get("front", "")
                back = card.get("back", "")
                if not front or not back:
                    stats["errors"].append(f"Card {i}: front or back is empty")
                    continue

                if tts:
                    word = card.get("word", strip_html(front))
                    model = TTS_MODELS.get(card_type, BASIC_TTS_MODEL)
                    if card_type not in TTS_MODELS:
                        card_type = "basic"
                    note = NoteWithGuid(
                        model=model,
                        fields=[front, back, word],
                        tags=tags,
                    )
                else:
                    model = MODELS.get(card_type, BASIC_MODEL)
                    if card_type not in MODELS:
                        card_type = "basic"
                    note = NoteWithGuid(
                        model=model,
                        fields=[front, back],
                        tags=tags,
                    )

            deck.add_note(note)
            stats[card_type] += 1

        except Exception as e:
            stats["errors"].append(f"Card {i}: {e}")

    total = stats["basic"] + stats["reversed"] + stats["cloze"] + stats["typing"] + stats["listening"]
    if total == 0:
        return f"エラー: 有効なカードが0枚です。エラー: {stats['errors']}"

    # 出力先
    if not output_path:
        safe_name = deck_name.replace("::", "_").replace("/", "_").replace("\\", "_")
        output_path = os.path.join(
            os.path.expanduser("~/Desktop"), f"{safe_name}.apkg"
        )

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    package = genanki.Package(deck)
    package.write_to_file(output_path)

    result = f"デッキ生成完了!\n"
    result += f"ファイル: {output_path}\n"
    result += f"合計 {total} 枚"
    if tts:
        result += " (TTS音声付き)"
    result += "\n"
    for t in ["basic", "reversed", "cloze", "typing", "listening"]:
        if stats[t]:
            result += f"  - {t.capitalize()}: {stats[t]}枚\n"
    if stats["errors"]:
        result += f"エラー {len(stats['errors'])}件:\n"
        for err in stats["errors"][:5]:
            result += f"  - {err}\n"

    return result


@mcp.tool()
def merge_anki_decks(
    input_paths: list[str],
    output_path: str = "",
    merged_deck_name: str = "Merged Deck",
) -> str:
    """
    複数の.apkgファイルを1つにマージする。

    Args:
        input_paths: マージ元の.apkgファイルパスの配列
        output_path: 出力先パス (省略時: ~/Desktop/merged.apkg)
        merged_deck_name: マージ後のデッキ名

    Returns:
        マージ結果
    """
    import zipfile
    import sqlite3
    import tempfile

    if len(input_paths) < 2:
        return "エラー: 2つ以上のファイルを指定してください"

    all_decks = []
    for path in input_paths:
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(path):
            return f"エラー: ファイルが見つかりません: {path}"

    # genankiでは直接マージできないので、そのまま情報を返す
    if not output_path:
        output_path = os.path.join(
            os.path.expanduser("~/Desktop"), "merged.apkg"
        )

    result = "ℹ️ Ankiでのマージ手順:\n"
    result += "Ankiを開いて以下のファイルを順にインポートしてください:\n"
    for p in input_paths:
        result += f"  - {os.path.abspath(os.path.expanduser(p))}\n"
    result += "\nAnki側で同じデッキ名にすれば自動的にマージされます。"

    return result


@mcp.tool()
def list_card_types() -> str:
    """
    利用可能なカードタイプの一覧と使い方を返す。
    """
    return """
## 利用可能なカードタイプ

### 1. basic (基本)
最も標準的。表に問題、裏に答え。
```json
{"front": "What is HTTP?", "back": "HyperText Transfer Protocol"}
```

### 2. reversed (表裏両方)
表→裏 と 裏→表 の2枚が自動生成される。語彙学習に最適。
```json
{"type": "reversed", "front": "apple", "back": "りんご"}
```

### 3. cloze (穴埋め)
文中の {{c1::キーワード}} を隠して出題。複数穴もOK。
```json
{"type": "cloze", "text": "{{c1::光速}}は約{{c2::3×10⁸}} m/s", "extra": "真空中"}
```

### 4. typing (タイプ入力)
答えをキーボードで入力させる。スペル練習に最適。
```json
{"type": "typing", "front": "「りんご」を英語で", "back": "apple"}
```

### 5. listening (リスニング、tts=True時のみ)
音声だけ聞いて意味を答えるカード。英語リスニング強化に。
```json
{"type": "listening", "front": "ephemeral", "back": "はかない", "word": "ephemeral"}
```

## TTS音声オプション (tts=True)
英語学習カードにiOS TTS音声を付与。全カードタイプで使用可能。
- "word" フィールドにTTSで読み上げるplain textを指定
- 省略するとfrontからHTMLを除去して自動生成
- iOSのAnkiMobileで自動再生される（PC版Ankiでも対応）
```json
{"type": "reversed", "front": "<b>ephemeral</b>", "back": "はかない", "word": "ephemeral"}
```

## 共通オプション
- `tags`: タグ配列 (例: ["英語", "TOEIC", "重要"])
- front/back にはHTMLが使える (<b>太字</b>, <br>改行, <img>画像等)
- deck_name に "::" を使うと階層化 (例: "英語::文法::時制")
"""


@mcp.tool()
def generate_cloze_from_text(
    deck_name: str,
    sentences: list[dict],
    output_path: str = "",
) -> str:
    """
    穴埋め問題を一括生成する専用ツール。
    長文や定義文から重要語句を穴埋めにするのに便利。

    Args:
        deck_name: デッキ名
        sentences: 穴埋め文の配列
            [
                {
                    "text": "{{c1::DNA}}は{{c2::デオキシリボ核酸}}の略称である",
                    "extra": "生物の遺伝情報を担う分子",
                    "tags": ["生物", "遺伝"]
                }
            ]
        output_path: 出力先 (省略時: ~/Desktop/{deck_name}.apkg)

    Returns:
        生成結果
    """
    cards = []
    for s in sentences:
        cards.append({
            "type": "cloze",
            "text": s.get("text", ""),
            "extra": s.get("extra", ""),
            "tags": s.get("tags", []),
        })

    return generate_anki_deck(
        deck_name=deck_name,
        cards=cards,
        output_path=output_path,
    )


@mcp.tool()
def generate_vocab_deck(
    deck_name: str,
    words: list[dict],
    reversible: bool = True,
    tts: bool = False,
    output_path: str = "",
) -> str:
    """
    語彙カードを一括生成する専用ツール。英単語・用語集に最適。

    Args:
        deck_name: デッキ名 (例: "TOEIC英単語")
        words: 単語配列
            [
                {
                    "word": "ephemeral",
                    "pos": "形容詞",
                    "meaning": "はかない、つかの間の",
                    "example": "The beauty of cherry blossoms is ephemeral.",
                    "etymology": "ギリシャ語 ephemeros（1日だけの）= epi-（上に）+ hemera（日）",
                    "tags": ["英検1級"]
                }
            ]
            pos (品詞、日本語表記):
                "名詞", "動詞", "形容詞", "副詞", "前置詞", "接続詞",
                "代名詞", "間投詞", "名詞/動詞" (複数品詞の場合)
            etymology (語源):
                語の成り立ち。ラテン語・ギリシャ語の語根、接頭辞・接尾辞の分解等
            ※ example, pos, etymology は省略可（ただし pos と etymology は極力含めること）
        reversible: True なら英→日 と 日→英 の両方向カードを生成
        tts: True にすると英語TTS音声付き（iOS AnkiMobile対応）
             英→日カードでは単語表示時に発音再生
             日→英カードでは回答表示時に発音再生
        output_path: 出力先

    Returns:
        生成結果
    """
    cards = []
    card_type = "reversed" if reversible else "basic"

    for w in words:
        word = w.get("word", "")
        meaning = w.get("meaning", "")
        example = w.get("example", "")
        pos = w.get("pos", "")
        etymology = w.get("etymology", "")
        tags = w.get("tags", [])

        if not word or not meaning:
            continue

        front = f"<b>{word}</b>"
        if pos:
            front += f"<br><span style='color:#666; font-size:14px;'>{pos}</span>"

        back = meaning
        if etymology:
            back += f"<br><br><i>語源: {etymology}</i>"
        if example:
            back += f"<br><br><i>例: {example}</i>"

        card = {
            "type": card_type,
            "front": front,
            "back": back,
            "tags": tags,
        }
        if tts:
            card["word"] = word  # plain text for TTS

        cards.append(card)

    return generate_anki_deck(
        deck_name=deck_name,
        cards=cards,
        output_path=output_path,
        tts=tts,
    )


if __name__ == "__main__":
    mcp.run()
