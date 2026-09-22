import sqlite3
import os
from datetime import date, datetime, timedelta
import bcrypt

DB_PATH = os.path.join(os.path.dirname(__file__), "farm.db")

CROP_STATUSES = ["Planted", "Growing", "Ready", "Harvested"]

EXPENSE_CATEGORIES = [
    "Seeds", "Fertilizer", "Pesticide", "Fuel", "Labor",
    "Maintenance", "Equipment", "Irrigation", "Transport", "Other",
]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_names(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cur.fetchall()}


def _migrate(conn):
    """Add columns introduced after the first release without losing data."""
    cur = conn.cursor()

    wanted = {
        "crops": [("expected_harvest_date", "TEXT")],
        "inventory": [("reorder_threshold", "REAL DEFAULT 0")],
        "sales": [("crop_id", "INTEGER")],
        "expenses": [("crop_id", "INTEGER")],
    }

    for table, columns in wanted.items():
        existing = _column_names(cur, table)
        for name, decl in columns:
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # Link legacy sales to crops by matching the free-text crop name.
    cur.execute("""
        UPDATE sales SET crop_id = (
            SELECT id FROM crops WHERE crops.name = sales.crop_name LIMIT 1
        ) WHERE crop_id IS NULL
    """)

    # Turn old manual low-stock flags into a reorder threshold at current qty.
    cur.execute("""
        UPDATE inventory SET reorder_threshold = quantity
        WHERE low_stock = 1 AND (reorder_threshold IS NULL OR reorder_threshold = 0)
    """)

    conn.commit()


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            area TEXT,
            planting_date TEXT,
            status TEXT,
            expected_harvest_date TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            low_stock INTEGER DEFAULT 0,
            reorder_threshold REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_name TEXT NOT NULL,
            quantity REAL,
            price REAL,
            sale_date TEXT,
            crop_id INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL,
            expense_date TEXT,
            description TEXT,
            crop_id INTEGER
        )
    """)

    # AI-generated crop care schedule (irrigation, fertilizer, pest checks...).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS crop_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_id INTEGER,
            crop_name TEXT,
            task_type TEXT,
            title TEXT,
            due_date TEXT,
            notes TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    # AI leaf-photo disease diagnoses logged against a crop.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_id INTEGER,
            crop_name TEXT,
            image_path TEXT,
            problem TEXT,
            severity TEXT,
            treatment TEXT,
            consult_agronomist INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    # Persistent AI chat transcripts (per user).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            role TEXT,
            text TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    _migrate(conn)
    conn.close()


def create_user(username, password):
    """Returns True if the account was created, False if the username is taken."""
    conn = get_connection()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(username, password):
    """Returns True if username/password match a stored user."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not row:
        return False

    return bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8"))


# ---------------------------------------------------------------------------
# Crops
# ---------------------------------------------------------------------------

def add_crop(name, area, planting_date, status, expected_harvest_date=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO crops (name, area, planting_date, status, expected_harvest_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, area, planting_date, status, expected_harvest_date)
    )
    crop_id = cur.lastrowid
    conn.commit()
    conn.close()
    return crop_id


def update_crop(crop_id, name, area, planting_date, status, expected_harvest_date=None):
    conn = get_connection()
    conn.execute(
        "UPDATE crops SET name = ?, area = ?, planting_date = ?, status = ?, "
        "expected_harvest_date = ? WHERE id = ?",
        (name, area, planting_date, status, expected_harvest_date, crop_id)
    )
    # Keep the denormalised crop name on linked sales in sync.
    conn.execute("UPDATE sales SET crop_name = ? WHERE crop_id = ?", (name, crop_id))
    conn.commit()
    conn.close()


def get_crops():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM crops ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def get_crop(crop_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM crops WHERE id = ?", (crop_id,)).fetchone()
    conn.close()
    return row


def delete_crop(crop_id):
    conn = get_connection()
    conn.execute("UPDATE sales SET crop_id = NULL WHERE crop_id = ?", (crop_id,))
    conn.execute("UPDATE expenses SET crop_id = NULL WHERE crop_id = ?", (crop_id,))
    conn.execute("DELETE FROM crop_tasks WHERE crop_id = ?", (crop_id,))
    conn.execute("DELETE FROM diagnoses WHERE crop_id = ?", (crop_id,))
    conn.execute("DELETE FROM crops WHERE id = ?", (crop_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def add_inventory_item(item_name, quantity, unit, reorder_threshold=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO inventory (item_name, quantity, unit, reorder_threshold) "
        "VALUES (?, ?, ?, ?)",
        (item_name, quantity, unit, reorder_threshold)
    )
    conn.commit()
    conn.close()


def update_inventory_item(item_id, item_name, quantity, unit, reorder_threshold=0):
    conn = get_connection()
    conn.execute(
        "UPDATE inventory SET item_name = ?, quantity = ?, unit = ?, "
        "reorder_threshold = ? WHERE id = ?",
        (item_name, quantity, unit, reorder_threshold, item_id)
    )
    conn.commit()
    conn.close()


def get_inventory():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM inventory ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def delete_inventory_item(item_id):
    conn = get_connection()
    conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def is_low_stock(item):
    """An item is low when its quantity is at or below its reorder threshold."""
    try:
        quantity = float(item["quantity"] or 0)
        threshold = float(item["reorder_threshold"] or 0)
    except (TypeError, ValueError, IndexError):
        return False
    return threshold > 0 and quantity <= threshold


def get_low_stock_items():
    return [item for item in get_inventory() if is_low_stock(item)]


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

def add_sale(crop_name, quantity, price, sale_date, crop_id=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO sales (crop_name, quantity, price, sale_date, crop_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (crop_name, quantity, price, sale_date, crop_id)
    )
    conn.commit()
    conn.close()


def update_sale(sale_id, crop_name, quantity, price, sale_date, crop_id=None):
    conn = get_connection()
    conn.execute(
        "UPDATE sales SET crop_name = ?, quantity = ?, price = ?, sale_date = ?, "
        "crop_id = ? WHERE id = ?",
        (crop_name, quantity, price, sale_date, crop_id, sale_id)
    )
    conn.commit()
    conn.close()


def get_sales():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def delete_sale(sale_id):
    conn = get_connection()
    conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
    conn.commit()
    conn.close()


def get_total_sales():
    conn = get_connection()
    row = conn.execute("SELECT SUM(quantity * price) as total FROM sales").fetchone()
    conn.close()
    return row["total"] or 0


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

def add_expense(category, amount, expense_date, description, crop_id=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO expenses (category, amount, expense_date, description, crop_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (category, amount, expense_date, description, crop_id)
    )
    conn.commit()
    conn.close()


def update_expense(expense_id, category, amount, expense_date, description, crop_id=None):
    conn = get_connection()
    conn.execute(
        "UPDATE expenses SET category = ?, amount = ?, expense_date = ?, "
        "description = ?, crop_id = ? WHERE id = ?",
        (category, amount, expense_date, description, crop_id, expense_id)
    )
    conn.commit()
    conn.close()


def get_expenses():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM expenses ORDER BY id DESC").fetchall()
    conn.close()
    return rows


def delete_expense(expense_id):
    conn = get_connection()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()


def get_total_expenses():
    conn = get_connection()
    row = conn.execute("SELECT SUM(amount) as total FROM expenses").fetchone()
    conn.close()
    return row["total"] or 0


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_total_profit():
    return get_total_sales() - get_total_expenses()


def get_profit_by_crop():
    """Profit per crop using the crop_id link on sales and expenses."""
    crops = get_crops()
    conn = get_connection()
    sales_rows = conn.execute(
        "SELECT crop_id, SUM(quantity * price) AS total FROM sales "
        "WHERE crop_id IS NOT NULL GROUP BY crop_id"
    ).fetchall()
    expense_rows = conn.execute(
        "SELECT crop_id, SUM(amount) AS total FROM expenses "
        "WHERE crop_id IS NOT NULL GROUP BY crop_id"
    ).fetchall()
    conn.close()

    sales_map = {r["crop_id"]: r["total"] or 0 for r in sales_rows}
    expense_map = {r["crop_id"]: r["total"] or 0 for r in expense_rows}

    result = []
    for crop in crops:
        revenue = sales_map.get(crop["id"], 0)
        cost = expense_map.get(crop["id"], 0)
        result.append({
            "id": crop["id"],
            "name": crop["name"],
            "sales": revenue,
            "expenses": cost,
            "profit": revenue - cost,
        })
    return result


def get_monthly_totals():
    """Return [(month 'YYYY-MM', sales, expenses), ...] sorted by month."""
    conn = get_connection()
    sales_rows = conn.execute(
        "SELECT substr(sale_date, 1, 7) AS month, SUM(quantity * price) AS total "
        "FROM sales WHERE sale_date IS NOT NULL AND sale_date != '' GROUP BY month"
    ).fetchall()
    expense_rows = conn.execute(
        "SELECT substr(expense_date, 1, 7) AS month, SUM(amount) AS total "
        "FROM expenses WHERE expense_date IS NOT NULL AND expense_date != '' "
        "GROUP BY month"
    ).fetchall()
    conn.close()

    sales_map = {r["month"]: r["total"] or 0 for r in sales_rows}
    expense_map = {r["month"]: r["total"] or 0 for r in expense_rows}
    months = sorted(set(sales_map) | set(expense_map))
    return [(m, sales_map.get(m, 0), expense_map.get(m, 0)) for m in months]


def get_expenses_by_category():
    """Return [(category, total), ...] ordered by amount descending."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses "
        "GROUP BY category ORDER BY total DESC"
    ).fetchall()
    conn.close()
    return [(r["category"], r["total"] or 0) for r in rows]


def days_until(date_str):
    """Days from today to an ISO date, or None if the date is missing/invalid."""
    if not date_str:
        return None
    try:
        target = datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (target - date.today()).days


# ---------------------------------------------------------------------------
# Crop care schedule (AI-generated calendar)
# ---------------------------------------------------------------------------

TASK_TYPES = ["Irrigation", "Fertilizer", "Pest check", "Harvest", "Other"]


def add_crop_task(crop_id, crop_name, task_type, title, due_date, notes=""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO crop_tasks (crop_id, crop_name, task_type, title, due_date, "
        "notes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (crop_id, crop_name, task_type, title, due_date, notes,
         datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def add_crop_tasks(crop_id, crop_name, tasks):
    """Bulk insert tasks. `tasks` is a list of dicts with task_type/title/due_date/notes."""
    conn = get_connection()
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO crop_tasks (crop_id, crop_name, task_type, title, due_date, "
        "notes, done, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        [
            (
                crop_id, crop_name,
                t.get("task_type") or "Other",
                t.get("title") or "",
                t.get("due_date"),
                t.get("notes") or "",
                now,
            )
            for t in tasks
        ]
    )
    conn.commit()
    conn.close()


def get_crop_tasks(crop_id=None):
    conn = get_connection()
    if crop_id is None:
        rows = conn.execute(
            "SELECT * FROM crop_tasks ORDER BY done, due_date, id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM crop_tasks WHERE crop_id = ? ORDER BY done, due_date, id",
            (crop_id,)
        ).fetchall()
    conn.close()
    return rows


def get_upcoming_tasks(days=14):
    """Open tasks due on or before today + `days` (includes overdue tasks)."""
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM crop_tasks WHERE done = 0 AND due_date IS NOT NULL "
        "AND due_date != '' AND due_date <= ? ORDER BY due_date ASC, id ASC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return rows


def mark_task_done(task_id, done=1):
    conn = get_connection()
    conn.execute("UPDATE crop_tasks SET done = ? WHERE id = ?", (1 if done else 0, task_id))
    conn.commit()
    conn.close()


def delete_crop_task(task_id):
    conn = get_connection()
    conn.execute("DELETE FROM crop_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def clear_crop_tasks(crop_id):
    conn = get_connection()
    conn.execute("DELETE FROM crop_tasks WHERE crop_id = ?", (crop_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Disease diagnoses (AI leaf-photo analysis)
# ---------------------------------------------------------------------------

def add_diagnosis(crop_id, crop_name, image_path, problem, severity, treatment,
                  consult_agronomist=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO diagnoses (crop_id, crop_name, image_path, problem, severity, "
        "treatment, consult_agronomist, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (crop_id, crop_name, image_path, problem, severity, treatment,
         1 if consult_agronomist else 0, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def get_diagnoses(crop_id=None):
    conn = get_connection()
    if crop_id is None:
        rows = conn.execute("SELECT * FROM diagnoses ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM diagnoses WHERE crop_id = ? ORDER BY id DESC", (crop_id,)
        ).fetchall()
    conn.close()
    return rows


def delete_diagnosis(diagnosis_id):
    conn = get_connection()
    conn.execute("DELETE FROM diagnoses WHERE id = ?", (diagnosis_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Persistent AI chat history
# ---------------------------------------------------------------------------

def add_chat_message(username, role, text):
    conn = get_connection()
    conn.execute(
        "INSERT INTO chat_messages (username, role, text, created_at) VALUES (?, ?, ?, ?)",
        (username, role, text, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def get_chat_messages(username, limit=None):
    """Return messages oldest-first. `limit` keeps only the most recent ones."""
    conn = get_connection()
    if limit:
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM chat_messages WHERE username = ? "
            "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (username, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE username = ? ORDER BY id ASC",
            (username,)
        ).fetchall()
    conn.close()
    return rows


def clear_chat_messages(username):
    conn = get_connection()
    conn.execute("DELETE FROM chat_messages WHERE username = ?", (username,))
    conn.commit()
    conn.close()
