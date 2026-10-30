-- PBL 隙間時間タスク提案アプリ / SQLite schema v0.1
-- 設計: API入力として利用可能時間（分）を受け取り、DBには保存しない。
--       提案の「内容」は登録済みuser_tasksのIDで記録する。
-- 注意: 外部キーはSQLite接続を確立するたびに PRAGMA foreign_keys=ON が必要。
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS task_libraries (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    description    TEXT
);

CREATE TABLE IF NOT EXISTS task_templates (
    id              INTEGER PRIMARY KEY,
    library_id      INTEGER NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    default_minutes INTEGER NOT NULL CHECK (default_minutes > 0),
    FOREIGN KEY (library_id) REFERENCES task_libraries(id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    UNIQUE (library_id, title)
);

CREATE TABLE IF NOT EXISTS user_tasks (
    id                INTEGER PRIMARY KEY,
    user_id           INTEGER NOT NULL,
    task_template_id  INTEGER NOT NULL,
    user_priority     INTEGER NOT NULL DEFAULT 3 CHECK (user_priority BETWEEN 1 AND 5),
    feedback_weight   REAL NOT NULL DEFAULT 1.0 CHECK (feedback_weight >= 0),
    estimated_minutes INTEGER CHECK (estimated_minutes > 0),
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (task_template_id) REFERENCES task_templates(id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    UNIQUE (user_id, task_template_id),
    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    suggested_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'rejected')),
    FOREIGN KEY (user_id) REFERENCES users(id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    UNIQUE (id, user_id)
);

CREATE TABLE IF NOT EXISTS suggestion_items (
    id             INTEGER PRIMARY KEY,
    suggestion_id  INTEGER NOT NULL,
    user_task_id   INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    display_order  INTEGER NOT NULL CHECK (display_order > 0),
    -- 複合外部キーで、提案した人とそのタスクの所有者が一致することを保証
    FOREIGN KEY (suggestion_id, user_id) REFERENCES suggestions(id, user_id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (user_task_id, user_id) REFERENCES user_tasks(id, user_id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    UNIQUE (suggestion_id, user_task_id),
    UNIQUE (suggestion_id, display_order)
);

CREATE TABLE IF NOT EXISTS feedback (
    id             INTEGER PRIMARY KEY,
    suggestion_id  INTEGER NOT NULL UNIQUE,
    rating         INTEGER CHECK (rating BETWEEN 1 AND 5),
    body           TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (suggestion_id) REFERENCES suggestions(id)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK (rating IS NOT NULL OR (body IS NOT NULL AND length(trim(body)) > 0))
);

CREATE INDEX IF NOT EXISTS ix_task_templates_library
  ON task_templates(library_id);
CREATE INDEX IF NOT EXISTS ix_user_tasks_user_active
  ON user_tasks(user_id, is_active);
CREATE INDEX IF NOT EXISTS ix_suggestions_user_at
  ON suggestions(user_id, suggested_at DESC);
CREATE INDEX IF NOT EXISTS ix_suggestion_items_suggestion
  ON suggestion_items(suggestion_id, display_order);
