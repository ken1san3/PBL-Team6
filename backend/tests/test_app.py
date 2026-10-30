import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.app import make_server
from backend.database import DEMO_TASKS, connect, initialize
from backend.suggestions import create_suggestion, list_history, list_tasks, select_tasks


def temporary_directory():
    # Keep test files inside the workspace, including in restricted environments.
    root = Path(__file__).resolve().parents[2] / ".runtime" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_directory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "test.db"
        self.user_id = initialize(self.db)

    def test_seed_is_repeatable_and_preserves_personal_changes(self):
        with connect(self.db) as conn:
            with conn:
                conn.execute("UPDATE user_tasks SET user_priority = 1 WHERE user_id = ?", (self.user_id,))
        self.assertEqual(initialize(self.db), self.user_id)
        with connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM user_tasks").fetchone()[0], len(DEMO_TASKS))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM task_libraries").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            self.assertEqual({task["user_priority"] for task in list_tasks(conn, self.user_id)}, {1})
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_time_limits_and_history_persistence(self):
        with connect(self.db) as conn:
            for minutes in [1, 2, 5, 20, 60, 1440]:
                result = create_suggestion(conn, self.user_id, minutes)
                self.assertLessEqual(result["total_minutes"], minutes)
                self.assertEqual(result["remaining_minutes"], minutes - result["total_minutes"])
                self.assertEqual(result["total_minutes"], sum(t["minutes"] for t in result["tasks"]))
                ids = [t["id"] for t in result["tasks"]]
                self.assertEqual(len(ids), len(set(ids)))
                if minutes == 1:
                    self.assertIsNone(result["id"])
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0], 0)
                else:
                    self.assertIsNotNone(result["id"])
                    saved = conn.execute("SELECT user_task_id, user_id, display_order FROM suggestion_items WHERE suggestion_id = ? ORDER BY display_order", (result["id"],)).fetchall()
                    self.assertEqual([row[0] for row in saved], ids)
                    self.assertTrue(all(row[1] == self.user_id for row in saved))
                    self.assertEqual([row[2] for row in saved], list(range(1, len(ids) + 1)))
        with connect(self.db) as conn:
            self.assertEqual(len(list_history(conn, self.user_id)), 5)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_personal_minutes_inactive_and_other_users(self):
        with connect(self.db) as conn:
            tasks = list_tasks(conn, self.user_id)
            self.assertEqual(next(t for t in tasks if t["title"] == "メールを整理する")["minutes"], 8)
            with conn:
                conn.execute("UPDATE user_tasks SET is_active = 0 WHERE user_id = ?", (self.user_id,))
                other = conn.execute("INSERT INTO users(email,password_hash) VALUES ('other@example.test','disabled')").lastrowid
                template = conn.execute("SELECT id FROM task_templates LIMIT 1").fetchone()[0]
                conn.execute("INSERT INTO user_tasks(user_id,task_template_id) VALUES (?,?)", (other, template))
            self.assertEqual(list_tasks(conn, self.user_id), [])
            result = create_suggestion(conn, self.user_id, 60)
            self.assertIsNone(result["id"])
            self.assertEqual(list_history(conn, self.user_id), [])

    def test_invalid_minutes_do_not_write_history(self):
        with connect(self.db) as conn:
            for value in [None, True, False, "20", 0, -1, 1.5, 20.0, 1441]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    create_suggestion(conn, self.user_id, value)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0], 0)

    def test_failed_item_insert_rolls_back_entire_suggestion(self):
        with connect(self.db) as conn:
            conn.executescript("CREATE TRIGGER fail_second_item BEFORE INSERT ON suggestion_items WHEN NEW.display_order = 2 BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END;")
            with self.assertRaises(sqlite3.IntegrityError):
                create_suggestion(conn, self.user_id, 20)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM suggestion_items").fetchone()[0], 0)

    def test_foreign_keys_reject_another_users_task(self):
        with connect(self.db) as conn:
            with conn:
                other = conn.execute("INSERT INTO users(email,password_hash) VALUES ('other@example.test','disabled')").lastrowid
                suggestion = conn.execute("INSERT INTO suggestions(user_id) VALUES (?)", (other,)).lastrowid
            task_id = list_tasks(conn, self.user_id)[0]["id"]
            with self.assertRaises(sqlite3.IntegrityError), conn:
                conn.execute("INSERT INTO suggestion_items(suggestion_id,user_task_id,user_id,display_order) VALUES (?,?,?,1)", (suggestion, task_id, other))


class SelectionTest(unittest.TestCase):
    def test_matches_exhaustive_search_including_tie_breaks(self):
        tasks = [
            {"id": 1, "minutes": 3, "user_priority": 3, "feedback_weight": 1.0},
            {"id": 2, "minutes": 5, "user_priority": 5, "feedback_weight": 0.5},
            {"id": 3, "minutes": 7, "user_priority": 3, "feedback_weight": 1.0},
            {"id": 4, "minutes": 2, "user_priority": 4, "feedback_weight": 0.0},
            {"id": 5, "minutes": 8, "user_priority": 5, "feedback_weight": 1.1},
        ]
        candidates = [t for t in tasks if t["feedback_weight"] > 0]
        for minutes in range(1, 26):
            groups = [group for count in range(len(candidates) + 1) for group in itertools.combinations(candidates, count) if sum(t["minutes"] for t in group) <= minutes]
            def rank(group):
                return (sum(t["user_priority"] * t["feedback_weight"] for t in group), sum(t["minutes"] for t in group), -len(group))
            with self.subTest(minutes=minutes):
                self.assertEqual(rank(select_tasks(tasks, minutes)), max(map(rank, groups)))


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = temporary_directory()
        cls.server = make_server(Path(cls.tmp.name) / "http.db", port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path, body=None, content_type="application/json", origin=None):
        headers = {"Content-Type": content_type}
        if origin:
            headers["Origin"] = origin
        req = Request(self.base + path, data=body, headers=headers)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read()

    def test_browser_page_and_end_to_end_api(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("タスクを提案する", body.decode())
        status, body = self.request("/api/health")
        self.assertEqual((status, json.loads(body)["status"]), (200, "ok"))
        status, body = self.request("/api/tasks")
        self.assertEqual(len(json.loads(body)["tasks"]), len(DEMO_TASKS))
        status, body = self.request("/api/suggestions", b'{"available_minutes":20}')
        self.assertEqual(status, 201)
        result = json.loads(body)
        self.assertLessEqual(result["total_minutes"], 20)
        status, body = self.request("/api/history")
        self.assertEqual(status, 200)
        history = json.loads(body)["history"]
        self.assertEqual(history[0]["id"], result["id"])
        self.assertEqual(history[0]["total_minutes"], result["total_minutes"])

    def test_bad_requests(self):
        for body in [b'{}', b'[]', b'bad json', b'{"available_minutes":true}', b'{"available_minutes":0}', b'{"available_minutes":20.5}', b'{"available_minutes":1441}']:
            with self.subTest(body=body):
                self.assertEqual(self.request("/api/suggestions", body)[0], 400)
        self.assertEqual(self.request("/api/suggestions", b'{}', content_type="text/plain")[0], 415)
        self.assertEqual(self.request("/api/suggestions", b'{}', origin="https://example.test")[0], 403)
        self.assertEqual(self.request("/missing")[0], 404)
        self.assertEqual(self.request("/api/suggestions", b'{"available_minutes":1}')[0], 200)


if __name__ == "__main__":
    unittest.main()
