"""Select tasks within a time budget and persist a suggestion atomically."""

import math


MAX_MINUTES = 1440


def validate_minutes(value):
    if type(value) is not int or not 1 <= value <= MAX_MINUTES:
        raise ValueError(f"空き時間は1〜{MAX_MINUTES}の整数（分）で入力してください。")
    return value


def list_tasks(conn, user_id):
    return [dict(row) for row in conn.execute(
        """SELECT ut.id, tt.title, tt.description, tl.name AS library,
                  COALESCE(ut.estimated_minutes, tt.default_minutes) AS minutes,
                  ut.user_priority, ut.feedback_weight
           FROM user_tasks ut
           JOIN task_templates tt ON tt.id = ut.task_template_id
           JOIN task_libraries tl ON tl.id = tt.library_id
           WHERE ut.user_id = ? AND ut.is_active = 1
           ORDER BY tl.id, ut.id""", (user_id,),
    )]


def select_tasks(tasks, available_minutes):
    """0/1 knapsack: maximize sum(priority * weight), then time utilization.

    Each registered task appears at most once. Zero-weight tasks are excluded.
    This deliberately favors several useful short tasks over one long task when
    their combined score is higher; the formula is a provisional demo policy.
    """
    validate_minutes(available_minutes)
    states = [None] * (available_minutes + 1)
    states[0] = (0.0, ())
    for index, task in enumerate(tasks):
        minutes = task["minutes"]
        score = task["user_priority"] * task["feedback_weight"]
        if not math.isfinite(score) or score <= 0 or minutes > available_minutes:
            continue
        for spent in range(available_minutes, minutes - 1, -1):
            previous = states[spent - minutes]
            if previous is None:
                continue
            candidate = (previous[0] + score, previous[1] + (index,))
            current = states[spent]
            if current is None or (candidate[0], -len(candidate[1])) > (current[0], -len(current[1])):
                states[spent] = candidate
    _, best = max(
        ((spent, state) for spent, state in enumerate(states) if state is not None),
        key=lambda item: (item[1][0], item[0], -len(item[1][1])),
    )
    selected = [dict(tasks[index]) for index in best[1]]
    selected.sort(key=lambda t: (-(t["user_priority"] * t["feedback_weight"]), t["minutes"], t["id"]))
    return selected


def create_suggestion(conn, user_id, available_minutes):
    validate_minutes(available_minutes)
    # Read candidates and save parent + items in one transaction.
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        selected = select_tasks(list_tasks(conn, user_id), available_minutes)
        total = sum(task["minutes"] for task in selected)
        result = {
            "id": None, "available_minutes": available_minutes,
            "total_minutes": total, "remaining_minutes": available_minutes - total,
            "tasks": selected,
        }
        if not selected:
            result["message"] = "この時間に収まるタスクがありません。空き時間を増やして試してください。"
            return result
        cursor = conn.execute("INSERT INTO suggestions(user_id) VALUES (?)", (user_id,))
        suggestion_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO suggestion_items(suggestion_id, user_task_id, user_id, display_order) VALUES (?, ?, ?, ?)",
            [(suggestion_id, task["id"], user_id, order) for order, task in enumerate(selected, 1)],
        )
        record = conn.execute("SELECT suggested_at, status FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        result.update(id=suggestion_id, suggested_at=record["suggested_at"], status=record["status"])
        return result


def list_history(conn, user_id, limit=10):
    results = []
    for row in conn.execute(
        "SELECT id, suggested_at, status FROM suggestions WHERE user_id = ? ORDER BY suggested_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    ):
        result = dict(row)
        result["tasks"] = [dict(item) for item in conn.execute(
            """SELECT ut.id, tt.title, COALESCE(ut.estimated_minutes, tt.default_minutes) AS minutes,
                      si.display_order
               FROM suggestion_items si
               JOIN user_tasks ut ON ut.id = si.user_task_id AND ut.user_id = si.user_id
               JOIN task_templates tt ON tt.id = ut.task_template_id
               WHERE si.suggestion_id = ? AND si.user_id = ? ORDER BY si.display_order""",
            (row["id"], user_id),
        )]
        result["total_minutes"] = sum(task["minutes"] for task in result["tasks"])
        results.append(result)
    return results
