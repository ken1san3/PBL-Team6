"""Run with: python backend/app.py [--port 8000] [--minutes 20]."""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys
import traceback
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import DEFAULT_DB, connect, initialize
from backend.suggestions import create_suggestion, list_history, list_tasks


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, db_path, user_id, **kwargs):
        self.db_path = db_path
        self.user_id = user_id
        super().__init__(*args, **kwargs)

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send_bytes(200, (Path(__file__).parent / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        with connect(self.db_path) as conn:
            if path == "/api/health":
                conn.execute("SELECT 1").fetchone()
                self.send_json(200, {"status": "ok", "database": "SQLite", "user_id": self.user_id})
            elif path == "/api/tasks":
                self.send_json(200, {"tasks": list_tasks(conn, self.user_id)})
            elif path == "/api/history":
                self.send_json(200, {"history": list_history(conn, self.user_id)})
            else:
                self.send_json(404, {"error": "ページが見つかりません。"})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/suggestions":
            self.send_json(404, {"error": "APIが見つかりません。"})
            return
        # Browser writes are same-origin. No cross-origin CORS permission is granted.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            self.send_json(403, {"error": "別のサイトからは操作できません。"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Content-Type: application/json を指定してください。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("リクエストのサイズが不正です。")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSONオブジェクトを送信してください。")
            with connect(self.db_path) as conn:
                result = create_suggestion(conn, self.user_id, data.get("available_minutes"))
            self.send_json(201 if result["id"] is not None else 200, result)
        except (ValueError, UnicodeDecodeError) as exc:
            self.send_json(400, {"error": str(exc) if not isinstance(exc, json.JSONDecodeError) else "JSONの形式が不正です。"})
        except sqlite3.Error:
            traceback.print_exc()
            self.send_json(500, {"error": "DBへの保存に失敗しました。もう一度お試しください。"})


def make_server(db_path=DEFAULT_DB, port=8000):
    user_id = initialize(db_path)
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, db_path=db_path, user_id=user_id))


def main():
    parser = argparse.ArgumentParser(description="PBL 空き時間タスク提案デモ")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--minutes", type=int, help="ブラウザを使わず提案を実行し、結果をJSONで表示")
    args = parser.parse_args()
    if args.minutes is not None:
        user_id = initialize(args.db)
        try:
            with connect(args.db) as conn:
                result = create_suggestion(conn, user_id, args.minutes)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    try:
        server = make_server(args.db, args.port)
    except OSError as exc:
        parser.exit(1, f"起動できませんでした: {exc}\n別のポートを --port 8001 のように指定できます。\n")
    print(f"PBL demo: http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Database: {args.db.resolve()}\nStop: Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
