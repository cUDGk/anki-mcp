"""
Anki Deck Generator MCP Server
任意のデータからAnkiデッキ(.apkg)を生成するMCPサーバー

出力先の制限:
  デフォルト出力ディレクトリは ~/Desktop。
  環境変数 ANKI_OUTPUT_DIR を設定するとそのディレクトリに変更できる。
  output_path を明示する場合も ANKI_OUTPUT_DIR 配下に限定される。

環境変数:
  ANKI_OUTPUT_DIR  許可する出力ルートディレクトリ (省略時: ~/Desktop)
  ANKI_CARD_LIMIT  1デッキに含めるカードの上限枚数 (省略時: 5000)
"""

import os
import re
import html
import hashlib
from pathlib import Path
from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

import genanki

try:
    import bleach
    _BLEACH_AVAILABLE = True
except ImportError:
    _BLEACH_AVAILABLE = False

# S1: CSS sanitizer to prevent CSS-based external resource loading via style attribute.
# Older bleach versions don't have css_sanitizer; fall back gracefully.
try:
    from bleach.css_sanitizer import CSSSanitizer
    _CSS_SANITIZER = CSSSanitizer(
        allowed_css_properties=[
            "color", "background-color", "font-size", "font-weight",
            "font-style", "font-family", "text-align", "text-decoration",
            "border", "border-color", "border-width", "border-style",
            "padding", "margin", "padding-left", "padding-right", "padding-top", "padding-bottom",
            "margin-left", "margin-right", "margin-top", "margin-bottom",
            "width", "height", "max-width", "max-height", "display",
        ]
    )
except ImportError:
    _CSS_SANITIZER = None

mcp = FastMCP("anki-deck-generator")

# ── 定数 ────────────────────────────────────────────────

_DEFAULT_OUTPUT_DIR = Path.home() / "Desktop"
_ANKI_OUTPUT_DIR = Path(os.environ.get("ANKI_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR))).expanduser().resolve()
_ANKI_CARD_LIMIT = int(os.environ.get("ANKI_CARD_LIMIT", "5000"))

# bleach の許可タグ・属性
_BLEACH_ALLOWED_TAGS = [
    "b", "i", "u", "br", "span", "table", "tr", "td", "th",
    "ul", "li", "ol", "code", "pre", "img",
]


def _allow_href(tag, name, value):
    # S1: javascript:/data:/vbscript: URI を href に通さない
    if name == "href" and re.match(r'^(javascript|data|vbscript):', value, re.I):
        return None
    return value


def _allow_img_src(tag, name, value):
    # S2: javascript: と data:非画像 を img src に通さない
    if name == "src" and re.match(r'^(javascript:|data:(?!image/))', value, re.I):
        return None
    return value


_BLEACH_ALLOWED_ATTRS = {
    "*": ["style", "class"],
    "img": _allow_img_src,
    "a": _allow_href,
}

# S5: 1 フィールドあたりのバイト/文字長制限（オーバーすると skip+error 記録）
_ANKI_FIELD_MAX = int(os.environ.get("ANKI_FIELD_MAX", str(64 * 1024)))


def _sanitize_html(text: str) -> str:
    """
    カードフィールドのHTMLをサニタイズする。
    bleach が利用可能であれば許可リストで洗浄する。
    注: Anki はカードテンプレートを HTML として描画するため、
        許可タグ内の XSS は依然としてリスクがある点に留意。
    S2: strip=True で危険タグの中身も丸ごと除去する（エスケープ表示で残さない）。
    S1: CSS sanitizer で style 属性経由の外部リソース読み込みを抑止する。
    """
    if not isinstance(text, str):
        text = str(text)
    if _BLEACH_AVAILABLE:
        kwargs = {
            "tags": _BLEACH_ALLOWED_TAGS,
            "attributes": _BLEACH_ALLOWED_ATTRS,
            "strip": True,
        }
        if _CSS_SANITIZER is not None:
            kwargs["css_sanitizer"] = _CSS_SANITIZER
        return bleach.clean(text, **kwargs)
    return text


def _strip_html(text: str) -> str:
    """HTMLタグを除去してplain textにする"""
    if _BLEACH_AVAILABLE:
        return bleach.clean(text, tags=[], strip=True)
    return re.sub(r'<[^>]+>', '', text).strip()


def _normalize_tags(raw: object) -> list[str]:
    """
    tags フィールドを list[str] に正規化する。
    - list 以外（str、None 等）は単一要素リストか空リストに変換
    - 各要素は str に強制キャスト
    - genanki は tags にスペースを含む文字列を許可しないため空白はアンダースコアに置換
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        # 文字列がそのまま渡されたら1タグとして扱う（char分解を防ぐ）
        raw = [raw]
    if not isinstance(raw, list):
        # tuple, set 等もリスト化
        try:
            raw = list(raw)
        except TypeError:
            return []
    # B4: str(t).strip() の真偽で空白のみを除外し、空白除去後の値を使う
    return [s.replace(" ", "_") for t in raw if t is not None for s in [str(t).strip()] if s]


# ── モデル定義 ──────────────────────────────────────────

def _model_id(name: str) -> int:
    """モデル名から決定論的IDを生成 (48-bit)"""
    return int(hashlib.md5(name.encode()).hexdigest()[:12], 16)


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
    """デッキ名から決定論的IDを生成 (48-bit)"""
    return int(hashlib.md5(f"deck_{name}".encode()).hexdigest()[:12], 16)


class NoteWithGuid(genanki.Note):
    """モデル名+全フィールドでGUIDを決定するNote（重複インポート防止）"""

    @property
    def guid(self):
        # C1: モデル名+全フィールドでGUIDを決定 — cloze非TTS/cloze+TTS間の衝突を防ぐ
        key = ":".join([self.model.name] + list(self.fields))
        return genanki.guid_for(key)


def _strip_cloze(text: str) -> str:
    """C2: cloze 構文 {{c1::content}} / {{c1::content::hint}} を content 部分に置換
    [^:}] でパイプ区切りヒント ("content|hint") も content として保持する"""
    return re.sub(r'\{\{c\d+::([^:}]+)(?:::[^}]*)?\}\}', r'\1', text)


def _sanitize_word(word: str) -> str:
    """
    S4: TTS 用 word フィールドから HTML タグと Anki テンプレート metachar ({, }) を除く。
    word は plain text として TTS エンジンに渡るので、HTML/テンプレート構文を含めると壊れる。
    """
    if not isinstance(word, str):
        word = str(word)
    # まず HTML を平文化
    plain = _strip_html(word)
    # Anki テンプレートの中括弧を除去（{{ や }} がフィールド値に混ざるとテンプレが破綻）
    return plain.replace("{", "").replace("}", "").strip()


# ── TypedDict ──────────────────────────────────────────

class CardInput(TypedDict, total=False):
    """generate_anki_deck に渡す cards 要素のスキーマ"""
    # U1: Literal で有効値を列挙（"listening" を追加）
    type: Literal["basic", "reversed", "cloze", "typing", "listening"]
    front: str
    back: str
    text: str        # cloze 用
    extra: str       # cloze 用
    word: str        # TTS 用 plain text
    tags: list


# ── パス検証ヘルパー ────────────────────────────────────

def _validate_output_path(output_path: str, deck_name: str) -> Path:
    """
    output_path を検証し、ANKI_OUTPUT_DIR 配下に限定した絶対パスを返す。
    output_path が空の場合はデフォルト (ANKI_OUTPUT_DIR/{safe_deck_name}.apkg) を使う。
    パス・トラバーサルや不正パスは ValueError を送出する。
    """
    if not output_path:
        # pathlib で safe なファイル名コンポーネントを取得してから違法文字を除去
        raw_name = Path(deck_name).name  # ディレクトリコンポーネントを除去
        # S5: 置換後が空文字になった場合は "deck" にフォールバック
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', raw_name) or "deck"
        resolved = (_ANKI_OUTPUT_DIR / f"{safe_name}.apkg").resolve()
    else:
        resolved = Path(output_path).expanduser().resolve()

    # S1: ANKI_OUTPUT_DIR 配下であることを強制（シンボリックリンク先も追う）
    try:
        resolved.relative_to(_ANKI_OUTPUT_DIR)
    except ValueError:
        raise ValueError(
            f"output_path は {_ANKI_OUTPUT_DIR} 配下でなければなりません: {resolved}"
        )

    # S3: シンボリックリンクを辿った実体パスで再検証
    real = resolved.resolve()
    try:
        real.relative_to(_ANKI_OUTPUT_DIR)
    except ValueError:
        raise ValueError(
            f"output_path resolves outside ANKI_OUTPUT_DIR: {real}"
        )

    # S5: ディレクトリ作成はパス検証の後
    parent = resolved.parent
    os.makedirs(parent, exist_ok=True)

    return resolved


# ── MCP ツール ──────────────────────────────────────────

@mcp.tool()
def generate_anki_deck(
    deck_name: str,
    cards: list[CardInput],
    output_path: str = "",
    description: str = "",
    tts: bool = False,
) -> str:
    """
    カードデータからAnkiデッキ(.apkg)を生成する。

    どんな教科・分野でもOK。Claude が事前にデータを解析して
    適切な cards 配列を組み立ててからこのツールを呼ぶ。

    出力先は ANKI_OUTPUT_DIR 配下（デフォルト: ~/Desktop）に限定される。

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
                ※ word を省略すると "" (空文字) が使われ TTS は無音になる

            ※ front/back にはHTMLも使える (<b>, <i>, <br>, <img>, <table>等)
            ※ tags は省略可能
        output_path: 出力先パス (省略時: ANKI_OUTPUT_DIR/<safe_deck_name>.apkg)
                     ※ safe_deck_name は deck_name から OS 不正文字を `_` に置換したもの
                     ANKI_OUTPUT_DIR 配下のパスのみ受け付ける
        description: デッキの説明 (Anki のデッキ一覧に表示される)
        tts: True にすると英語TTS音声付きカードを生成（PC版 Anki / iOS AnkiMobile 両対応）
             カード表示時に Anki 内蔵 TTS エンジンで英単語を読み上げる
             ※ {{tts ...}} 構文は Anki 2.1.20+ が必要

    Returns:
        生成されたファイルのパスと統計情報
    """
    # B4: 空チェックを上限チェックより先に行う
    if not cards:
        raise ValueError("カードが空です")

    # S8: カード数上限チェック
    if len(cards) > _ANKI_CARD_LIMIT:
        raise ValueError(
            f"カード数 {len(cards)} が上限 {_ANKI_CARD_LIMIT} を超えています"
        )

    # B3: deck_name は空白除去した値を以降全て使う（_deck_id, パス生成に影響）
    deck_name = deck_name.strip() if isinstance(deck_name, str) else ""
    if not deck_name:
        raise ValueError("deck_name を指定してください")

    # U4: listening を含む & tts が無効 → カードループに入る前に早期エラー
    if not tts:
        for i, card in enumerate(cards):
            if isinstance(card, dict) and card.get("type") == "listening":
                raise ValueError(
                    f"listening カード (index {i}) は tts=True が必要です"
                )

    deck = genanki.Deck(_deck_id(deck_name), deck_name, description=description)

    stats: dict = {"basic": 0, "reversed": 0, "cloze": 0, "typing": 0, "listening": 0, "errors": []}

    def _field_too_long(label: str, value: str, idx: int) -> bool:
        """S5: 1 フィールドが上限を超えたらエラーとして記録し True を返す"""
        if len(value) > _ANKI_FIELD_MAX:
            stats["errors"].append(
                f"Card {idx}: {label} が {len(value)} 文字で上限 {_ANKI_FIELD_MAX} を超過"
            )
            return True
        return False

    for i, card in enumerate(cards):
        # B4: dict 型チェック
        if not isinstance(card, dict):
            stats["errors"].append(f"Card {i}: dict ではありません (type={type(card).__name__})")
            continue
        try:
            # C4: card_type を正規化（str化・前後空白除去・小文字化）
            card_type = str(card.get("type", "basic")).strip().lower()
            tags = _normalize_tags(card.get("tags"))

            # U2: known_types は MODELS + TTS_MODELS のキー和集合
            known_types = set(MODELS.keys()) | set(TTS_MODELS.keys())
            if card_type not in known_types:
                stats["errors"].append(
                    f"Card {i}: 未知の card_type '{card_type}' (有効: {sorted(known_types)})"
                )
                continue

            if card_type == "cloze":
                text = _sanitize_html(card.get("text", ""))
                extra = _sanitize_html(card.get("extra", ""))
                if not text:
                    stats["errors"].append(f"Card {i}: cloze text is empty")
                    continue
                if _field_too_long("cloze text", text, i) or _field_too_long("cloze extra", extra, i):
                    continue
                if tts:
                    # S4: word は plain text 化 + Anki metachar 除去
                    raw_word = card.get("word", "")
                    word = _sanitize_word(str(raw_word))
                    # B5: cloze + tts で word が空なら text から自動導出（{{c\d+::content}} → content）
                    if not word:
                        derived = _sanitize_word(_strip_cloze(str(card.get("text", ""))))
                        if derived:
                            word = derived
                        else:
                            stats["errors"].append(
                                f"Card {i}: cloze + tts だが word を導出できませんでした"
                            )
                            continue  # C3: word が空のままノートを作らない
                    if _field_too_long("word", word, i):
                        continue
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
                # tts チェックは関数冒頭で早期 raise 済みなので到達時は tts=True 確定
                front = _sanitize_html(card.get("front", ""))
                back = _sanitize_html(card.get("back", ""))
                word = _sanitize_word(str(card.get("word", "")))
                # B2: front/back それぞれ個別メッセージ
                if not front:
                    stats["errors"].append(f"Card {i}: listening front is empty")
                if not back:
                    stats["errors"].append(f"Card {i}: listening back is empty")
                if not front or not back:
                    continue
                if (_field_too_long("front", front, i)
                        or _field_too_long("back", back, i)
                        or _field_too_long("word", word, i)):
                    continue
                note = NoteWithGuid(
                    model=LISTENING_MODEL,
                    fields=[front, back, word],
                    tags=tags,
                )
            else:
                front = _sanitize_html(card.get("front", ""))
                back = _sanitize_html(card.get("back", ""))
                if not front or not back:
                    stats["errors"].append(f"Card {i}: front or back is empty")
                    continue
                if _field_too_long("front", front, i) or _field_too_long("back", back, i):
                    continue

                if tts:
                    # S4: word は plain text 化 + Anki metachar 除去
                    word = _sanitize_word(str(card.get("word", "")))
                    if _field_too_long("word", word, i):
                        continue
                    model = TTS_MODELS[card_type]
                    note = NoteWithGuid(
                        model=model,
                        fields=[front, back, word],
                        tags=tags,
                    )
                else:
                    model = MODELS[card_type]
                    note = NoteWithGuid(
                        model=model,
                        fields=[front, back],
                        tags=tags,
                    )

            deck.add_note(note)
            # B3: stats キーが存在しない card_type はデフォルト "basic" にフォールバック
            stats_key = card_type if card_type in stats else "basic"
            stats[stats_key] += 1

        except (KeyError, ValueError, TypeError) as e:
            stats["errors"].append(f"Card {i}: {e}")
        except Exception as e:
            # 予期しない例外はログして再 raise（MemoryError 等を握り潰さない）
            stats["errors"].append(f"Card {i}: unexpected error: {e}")
            raise

    total = stats["basic"] + stats["reversed"] + stats["cloze"] + stats["typing"] + stats["listening"]
    if total == 0:
        raise ValueError(f"有効なカードが0枚です。エラー: {stats['errors']}")

    # S1/S2/S5: パス検証（makedirs もここで実行）
    resolved_path = _validate_output_path(output_path, deck_name)

    package = genanki.Package(deck)
    package.write_to_file(str(resolved_path))

    result = "デッキ生成完了!\n"
    result += f"ファイル: {resolved_path}\n"
    result += f"合計 {total} 枚"
    if tts:
        result += " (TTS音声付き)"
    result += "\n"
    for t in ["basic", "reversed", "cloze", "typing", "listening"]:
        if stats[t]:
            result += f"  - {t.capitalize()}: {stats[t]}枚\n"
    if stats["errors"]:
        result += f"エラー {len(stats['errors'])}件:\n"
        # B3: 5件超は件数を追記して表示
        errs = stats["errors"][:5]
        extra = len(stats["errors"]) - 5
        if extra > 0:
            errs.append(f"... and {extra} more")
        result += "\n".join(f"  • {e}" for e in errs) + "\n"

    return result


@mcp.tool()
def merge_anki_decks(
    input_paths: list[str],
    output_path: str = "",
    merged_deck_name: str = "Merged Deck",
) -> str:
    """
    複数の.apkgファイルを1つにマージする手順を案内する。

    注意: このツールは実際にファイルをマージするのではなく、
    Anki アプリ上で手動マージを行うための手順を返す。

    Args:
        input_paths: マージ元の.apkgファイルパスの配列
        output_path: (任意) エクスポート先の目安として案内文に表示される。実ファイル操作は行わない
        merged_deck_name: マージ後のデッキ名 (案内文に表示)

    Returns:
        Ankiでのマージ手順
    """
    if len(input_paths) < 2:
        raise ValueError("2つ以上のファイルを指定してください")

    # S6: input_paths は ANKI_OUTPUT_DIR 配下 + .apkg 拡張子のみ受け付ける
    invalid: list[str] = []
    resolved_paths: list[Path] = []
    for path in input_paths:
        resolved = Path(path).expanduser().resolve()
        if resolved.suffix.lower() != ".apkg":
            invalid.append(f"{resolved} (拡張子が .apkg ではありません)")
            continue
        try:
            resolved.relative_to(_ANKI_OUTPUT_DIR)
        except ValueError:
            invalid.append(f"{resolved} ({_ANKI_OUTPUT_DIR} 配下ではありません)")
            continue
        resolved_paths.append(resolved)
    if invalid:
        invalid_list = "\n".join(f"  - {p}" for p in invalid)
        raise ValueError(f"以下のパスは受け付けられません:\n{invalid_list}")

    # S11: 全ファイルの存在を確認し、欠落を全部まとめて報告
    missing = [str(p) for p in resolved_paths if not p.exists()]
    if missing:
        missing_list = "\n".join(f"  - {p}" for p in missing)
        raise ValueError(f"以下のファイルが見つかりません:\n{missing_list}")

    # S4: ユーザー提供値を html.escape してインジェクションを防ぐ
    safe_deck_name = html.escape(merged_deck_name)
    safe_output = html.escape(output_path.strip()) if output_path else ""
    target_label = safe_output if safe_output else f"(任意) {safe_deck_name}.apkg"
    result = f"ℹ️ Ankiでのマージ手順 (マージ後のデッキ名: {safe_deck_name}):\n"
    result += "Ankiを開いて以下のファイルを順にインポートしてください:\n"
    for p in resolved_paths:
        result += f"  - {p}\n"
    result += f"\nAnki側でデッキ名を「{safe_deck_name}」に統一すると自動的にマージされます。"
    result += f"\nエクスポート先の目安: {target_label}"

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
- 省略すると "" (空文字) が使われ TTS は無音になる
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
    tts: bool = False,
    description: str = "",
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
        output_path: 出力先 (省略時: ANKI_OUTPUT_DIR/<safe_deck_name>.apkg)
        tts: True にすると英語TTS音声付きカードを生成
        description: デッキの説明文 (generate_anki_deck に転送)

    Returns:
        生成結果（スキップされたエントリ数も併記）
    """
    cards: list[CardInput] = []
    skipped = 0
    for idx, s in enumerate(sentences):
        # B11: text が空のエントリをスキップ（空カードを append して error ログに乗せる必要はない）
        if not isinstance(s, dict):
            skipped += 1
            continue
        text = s.get("text", "")
        if not text:
            skipped += 1
            continue
        # B6: ここで _normalize_tags を呼ばず、generate_anki_deck 側に正規化を一任する
        cards.append({
            "type": "cloze",
            "text": text,
            "extra": s.get("extra", ""),
            "tags": s.get("tags"),
        })

    result = generate_anki_deck(
        deck_name=deck_name,
        cards=cards,
        output_path=output_path,
        description=description,
        tts=tts,
    )
    # U10: スキップ件数を結果に追記
    if skipped:
        result += f"スキップ {skipped}件 (非dict or text空)\n"
    return result


@mcp.tool()
def generate_vocab_deck(
    deck_name: str,
    words: list[dict],
    reversible: bool = True,
    output_path: str = "",
    tts: bool = False,
    description: str = "",
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
        output_path: 出力先 (省略時: ANKI_OUTPUT_DIR/<safe_deck_name>.apkg)
        tts: True にすると英語TTS音声付き（PC版 Anki / iOS AnkiMobile 両対応）
             英→日カードでは単語表示時に発音再生
             日→英カードでは回答表示時に発音再生
        description: デッキの説明文 (generate_anki_deck に転送)

    Returns:
        生成結果
    """
    cards: list[CardInput] = []
    card_type = "reversed" if reversible else "basic"

    for w in words:
        word = w.get("word", "")
        meaning = w.get("meaning", "")
        # S9: pos/etymology/example は HTML エスケープしてから挿入
        example = html.escape(w.get("example", ""))
        pos = html.escape(w.get("pos", ""))
        etymology = html.escape(w.get("etymology", ""))
        # B6: ここで _normalize_tags を呼ばず、generate_anki_deck 側に正規化を一任する
        tags = w.get("tags")

        if not word or not meaning:
            continue

        front = f"<b>{html.escape(word)}</b>"
        if pos:
            front += f"<br><span style='color:#666; font-size:14px;'>{pos}</span>"

        # B5: back 全体を組み立ててから一度だけ _sanitize_html を適用
        back = meaning
        if etymology:
            back += f"<br><br><i>語源: {etymology}</i>"
        if example:
            back += f"<br><br><i>例: {example}</i>"
        back = _sanitize_html(back)

        card: CardInput = {
            "type": card_type,
            "front": front,
            "back": back,
            "tags": tags,
        }
        if tts:
            # S4: TTS 用 word は plain text 化 + Anki metachar 除去
            card["word"] = _sanitize_word(word)

        cards.append(card)

    return generate_anki_deck(
        deck_name=deck_name,
        cards=cards,
        output_path=output_path,
        description=description,
        tts=tts,
    )


if __name__ == "__main__":
    mcp.run()
