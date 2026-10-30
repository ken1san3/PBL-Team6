"""SQLite connections and repeatable demo data initialization."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "database" / "PBL.db"
DEMO_EMAIL = "demo@pbl.local"

# library, title, description, standard minutes, priority, personal minutes
DEMO_TASKS = [
    ("学習", "英単語を5個復習する", "単語帳を開いて、意味を声に出して確認する。", 5, 4, None),
    ("学習", "技術記事を1本読む", "気になっていた記事を読み、要点を一つメモする。", 15, 4, None),
    ("学習", "プログラミング問題を1問解く", "短い練習問題に取り組む。", 25, 5, None),
    ("学習", "授業ノートを見直す", "前回の授業の重要なポイントを確認する。", 10, 3, None),
    ("学習", "読書を進める", "しおりの位置から集中して読む。", 20, 3, None),
    ("学習", "資格試験の模擬問題を解く", "問題を解き、間違えた箇所を確認する。", 45, 5, None),
    ("生活", "机の上を片付ける", "不要なものを戻して作業スペースを確保する。", 5, 3, None),
    ("生活", "メールを整理する", "不要なメールを整理し、要返信を確認する。", 10, 3, 8),
    ("生活", "部屋を掃除する", "床や棚の気になる場所を掃除する。", 20, 3, None),
    ("生活", "洗濯物をたたむ", "乾いた洗濯物をたたんで収納する。", 10, 2, None),
    ("生活", "買い物リストを作る", "冷蔵庫と日用品を確認してメモする。", 5, 2, None),
    ("生活", "作り置きを1品作る", "簡単なおかずを作って保存する。", 30, 3, None),
    ("健康", "水を飲んで姿勢を整える", "水分をとり、座り方を整える。", 2, 2, None),
    ("健康", "肩と首をストレッチする", "無理のない範囲でゆっくり体を動かす。", 3, 4, None),
    ("健康", "短い散歩をする", "屋外を歩いて気分転換する。", 15, 4, 12),
    ("健康", "軽い筋トレをする", "自分のペースで軽く体を動かす。", 10, 3, None),
    ("健康", "目を休める", "画面から離れて遠くを眺める。", 2, 3, None),
    ("健康", "ゆっくり入浴する", "湯船につかってリラックスする。", 30, 2, None),
    ("計画・趣味", "今日のやることを整理する", "残りの予定を確認して優先順位をつける。", 5, 5, None),
    ("計画・趣味", "日記を書く", "今日の出来事や気づきを記録する。", 10, 3, None),
    ("計画・趣味", "旅行の行き先を調べる", "行ってみたい場所を調べて候補を保存する。", 20, 2, None),
    ("計画・趣味", "スケッチを描く", "身近なものを一つ選んで描く。", 15, 2, None),
    ("計画・趣味", "来週の予定を立てる", "予定と締切を確認して一週間を組み立てる。", 25, 4, None),
    ("計画・趣味", "趣味の制作を進める", "途中になっている作品を進める。", 60, 4, None),
    ("健康", "ジムに行く", "ジムでトレーニングする。移動や着替えが必要な場合は別途時間を確保する。", 30, 5, None),
    ("健康", "ランニングをする", "準備運動をして、自分のペースで走る。", 45, 4, None),
    ("健康", "プールで泳ぐ", "プールで泳いで体を動かす。移動時間は含まない。", 60, 4, None),
    ("学習", "授業の予習・復習をする", "教科書とノートを使って、一回分の授業内容を整理する。", 30, 4, None),
    ("学習", "レポートを書く", "課題の資料を確認し、構成を考えて本文を書き進める。", 60, 5, None),
    ("学習", "開発プロジェクトを進める", "まとまった時間を使って、担当機能の実装や動作確認を進める。", 90, 5, None),
    ("生活", "スーパーへ買い物に行く", "近所のスーパーで食材や日用品を買う。往復の移動を含む目安。", 30, 3, None),
    ("生活", "夕食を作る", "食材の下準備から調理まで、夕食を一食分作る。", 45, 4, None),
    ("生活", "部屋全体を掃除する", "掃除機がけや水回りなど、部屋全体をまとめて掃除する。", 60, 3, None),
    ("計画・趣味", "楽器の練習をする", "基礎練習をして、練習中の曲を通して演奏する。", 30, 3, None),
    ("計画・趣味", "ドラマを1話観る", "気になっているドラマを一話分楽しむ。", 60, 2, None),
    ("計画・趣味", "イラストを制作する", "構図を考え、下描きや色塗りなど作品制作を進める。", 90, 3, None),
]


@contextmanager
def connect(db_path=DEFAULT_DB):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def initialize(db_path=DEFAULT_DB):
    """Create missing schema and demo records, without resetting existing data."""
    with connect(db_path) as conn:
        conn.executescript((ROOT / "database" / "PBL_schema.sql").read_text(encoding="utf-8-sig"))
        with conn:
            # No login endpoint: this account is only a local demo identity.
            conn.execute(
                "INSERT INTO users(email, password_hash) VALUES (?, ?) "
                "ON CONFLICT(email) DO NOTHING",
                (DEMO_EMAIL, "!disabled-local-demo-account"),
            )
            user_id = conn.execute("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()[0]
            for library, title, description, minutes, priority, personal_minutes in DEMO_TASKS:
                conn.execute(
                    "INSERT INTO task_libraries(name, description) VALUES (?, ?) "
                    "ON CONFLICT(name) DO NOTHING", (library, f"{library}のサンプルタスク"),
                )
                library_id = conn.execute("SELECT id FROM task_libraries WHERE name = ?", (library,)).fetchone()[0]
                conn.execute(
                    "INSERT INTO task_templates(library_id, title, description, default_minutes) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(library_id, title) DO NOTHING", (library_id, title, description, minutes),
                )
                template_id = conn.execute(
                    "SELECT id FROM task_templates WHERE library_id = ? AND title = ?", (library_id, title),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO user_tasks(user_id, task_template_id, user_priority, estimated_minutes) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(user_id, task_template_id) DO NOTHING",
                    (user_id, template_id, priority, personal_minutes),
                )
        return user_id
