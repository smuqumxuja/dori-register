from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import sys
import traceback
import zipfile
from html import escape as xml_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "journal.db"

SESSION_COOKIE = "journal_session"
SESSION_HOURS = 12
CAPTCHA_MINUTES = 5
DEFAULT_SUPER_USERNAME = os.environ.get("JOURNAL_SUPER_USERNAME", "superadmin")
DEFAULT_SUPER_PASSWORD = os.environ.get("JOURNAL_SUPER_PASSWORD", "Admin123!")

ROLES = {
    "super_admin": "Super admin",
    "local_admin": "Korpus local admini",
    "nurse": "Hamshira",
    "observer": "Kuzatuvchi",
}

CREATABLE_ROLES = {
    "local_admin": ROLES["local_admin"],
    "nurse": ROLES["nurse"],
    "observer": ROLES["observer"],
}

MEDICINE_FORMS = ["ampula", "tabletka", "ml", "mg", "flakon", "kapsula", "paket", "tomchi"]

ENTRY_FIELDS = [
    "medicine_id",
    "entry_date",
    "entry_time",
    "patient_name",
    "patient_id",
    "department",
    "nurse_name",
    "medicine_name",
    "dose",
    "quantity",
    "unit",
    "route",
    "prescription_no",
    "note",
]

XLSX_HEADERS = [
    "ID",
    "Sana",
    "Vaqt",
    "Bemor F.I.Sh.",
    "Bemor ID",
    "Bo'lim",
    "Hamshira",
    "Dori nomi",
    "Doza",
    "Miqdor",
    "Shakli",
    "Yuborish yo'li",
    "Retsept/Tayinlov",
    "Izoh",
    "Yaratilgan vaqt",
]

MEDICINE_XLSX_HEADERS = [
    "ID",
    "Bo'lim",
    "Dori nomi",
    "Qabul qilingan sana",
    "Qabul qilingan vaqt",
    "Shakli",
    "Qabul qilingan miqdor",
    "Real qoldiq",
    "Izoh",
]


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_id INTEGER,
                entry_date TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                patient_name TEXT NOT NULL,
                patient_id TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                nurse_name TEXT NOT NULL,
                medicine_name TEXT NOT NULL,
                dose TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                route TEXT NOT NULL DEFAULT '',
                prescription_no TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(medicine_id) REFERENCES medicines(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                building TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buildings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                name TEXT NOT NULL,
                received_date TEXT NOT NULL,
                received_time TEXT NOT NULL,
                form TEXT NOT NULL,
                initial_quantity REAL NOT NULL,
                remaining_quantity REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT NOT NULL DEFAULT '',
                building TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS captcha_challenges (
                token TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT '',
                entity_id INTEGER,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        migrate_schema(conn)
        seed_missing_created_by(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(entry_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_medicine ON entries(medicine_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_department ON entries(department)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_medicine_id ON entries(medicine_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_created_by ON entries(created_by)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_departments_name ON departments(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_departments_building ON departments(building)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_buildings_name ON buildings(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_medicines_department ON medicines(department)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_medicines_name ON medicines(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_medicines_remaining ON medicines(remaining_quantity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_medicines_created_by ON medicines(created_by)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_captcha_expires ON captcha_challenges(expires_at)")
        seed_departments_from_existing(conn)
        seed_buildings_from_departments(conn)
        ensure_initial_super_admin(conn)
        normalize_existing_users(conn)
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso(),))
        conn.execute("DELETE FROM captcha_challenges WHERE expires_at <= ?", (now_iso(),))
        conn.commit()


def migrate_schema(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "entries", "medicine_id", "INTEGER")
    ensure_column(conn, "entries", "created_by", "INTEGER")
    ensure_column(conn, "medicines", "created_by", "INTEGER")
    ensure_column(conn, "users", "building", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "users", "created_by", "INTEGER")
    conn.execute("UPDATE users SET role = 'local_admin' WHERE role = 'department_admin'")


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_missing_created_by(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE entries
        SET created_by = (
            SELECT users.id
            FROM users
            WHERE lower(users.full_name) = lower(entries.nurse_name)
            LIMIT 1
        )
        WHERE created_by IS NULL
          AND EXISTS (
            SELECT 1
            FROM users
            WHERE lower(users.full_name) = lower(entries.nurse_name)
          )
        """
    )


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def role_label(role: str) -> str:
    return ROLES.get(role, role)


def is_super_admin(user: dict[str, Any] | sqlite3.Row) -> bool:
    return user["role"] == "super_admin"


def can_write(user: dict[str, Any] | sqlite3.Row) -> bool:
    return user["role"] in {"super_admin", "local_admin", "nurse"}


def can_manage_users(user: dict[str, Any] | sqlite3.Row) -> bool:
    return user["role"] in {"super_admin", "local_admin"}


def can_manage_departments(user: dict[str, Any] | sqlite3.Row) -> bool:
    return is_super_admin(user)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def ensure_initial_super_admin(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1").fetchone()
    if existing:
        return

    now = now_iso()
    username_row = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_SUPER_USERNAME,)).fetchone()
    if username_row:
        conn.execute(
            """
            UPDATE users
            SET role = 'super_admin',
                department = '',
                building = '',
                is_active = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (now, username_row[0]),
        )
        return

    conn.execute(
        """
        INSERT INTO users (username, full_name, password_hash, role, department, building, is_active, created_at, updated_at)
        VALUES (?, ?, ?, 'super_admin', '', '', 1, ?, ?)
        """,
        (DEFAULT_SUPER_USERNAME, "Super Admin", hash_password(DEFAULT_SUPER_PASSWORD), now, now),
    )


def normalize_existing_users(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT users.id, users.department, users.building, departments.building AS dept_building
        FROM users
        LEFT JOIN departments ON lower(departments.name) = lower(users.department)
        WHERE users.building = ''
          AND users.department != ''
          AND COALESCE(departments.building, '') != ''
        """
    ).fetchall()
    for row in rows:
        conn.execute("UPDATE users SET building = ? WHERE id = ?", (row[3], row[0]))


def seed_departments_from_existing(conn: sqlite3.Connection) -> None:
    now = now_iso()
    rows = conn.execute(
        """
        SELECT DISTINCT department AS name FROM entries WHERE department != ''
        UNION
        SELECT DISTINCT department AS name FROM users WHERE department != ''
        UNION
        SELECT DISTINCT department AS name FROM medicines WHERE department != ''
        """
    ).fetchall()
    for row in rows:
        name = str(row[0]).strip()
        if not name:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO departments (name, building, note, created_at, updated_at)
            VALUES (?, '', '', ?, ?)
            """,
            (name, now, now),
        )


def seed_buildings_from_departments(conn: sqlite3.Connection) -> None:
    now = now_iso()
    rows = conn.execute(
        """
        SELECT DISTINCT building
        FROM departments
        WHERE building != ''
        UNION
        SELECT DISTINCT building
        FROM users
        WHERE building != ''
        """
    ).fetchall()
    for row in rows:
        name = str(row[0]).strip()
        if not name:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO buildings (name, note, created_at, updated_at)
            VALUES (?, '', ?, ?)
            """,
            (name, now, now),
        )


def department_to_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "building": row["building"],
        "note": row["note"],
    }


def building_to_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "note": row["note"],
    }


def medicine_to_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for key in ("initial_quantity", "remaining_quantity"):
        value = float(data[key])
        data[key] = int(value) if value.is_integer() else round(value, 3)
    return data


def medicine_row_to_public(row: sqlite3.Row, user: dict[str, Any]) -> dict[str, Any]:
    data = medicine_to_public(row)
    data["can_edit"] = can_edit_medicine(user, row)
    return data


def department_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM departments WHERE lower(name) = lower(?)", (name,)).fetchone())


def building_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM buildings WHERE lower(name) = lower(?)", (name,)).fetchone())


def user_to_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    role = row["role"]
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": role,
        "role_label": role_label(role),
        "department": row["department"],
        "building": row["building"],
        "created_by": row["created_by"] if "created_by" in row.keys() else None,
        "is_active": bool(row["is_active"]),
    }


def permissions_for(user: dict[str, Any]) -> dict[str, bool]:
    return {
        "can_write": can_write(user),
        "can_manage_users": can_manage_users(user),
        "can_manage_departments": can_manage_departments(user),
        "can_export": True,
    }


def role_options_for(user: dict[str, Any]) -> dict[str, str]:
    if is_super_admin(user):
        return CREATABLE_ROLES
    if user["role"] == "local_admin":
        return {key: CREATABLE_ROLES[key] for key in ("nurse", "observer")}
    return {}


def log_action(
    conn: sqlite3.Connection,
    user: dict[str, Any] | sqlite3.Row | None,
    action: str,
    entity_type: str = "",
    entity_id: int | None = None,
    description: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs (
            user_id, username, full_name, role, action, entity_type, entity_id, description, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"] if user else None,
            user["username"] if user else "",
            user["full_name"] if user else "",
            user["role"] if user else "",
            action,
            entity_type,
            entity_id,
            description,
            now_iso(),
        ),
    )


def visible_departments(user: dict[str, Any]) -> list[str]:
    with connect_db() as conn:
        return visible_departments_with_conn(conn, user)


def visible_departments_with_conn(conn: sqlite3.Connection, user: dict[str, Any]) -> list[str]:
    if is_super_admin(user):
        rows = conn.execute("SELECT name FROM departments ORDER BY name COLLATE NOCASE").fetchall()
        return [row["name"] for row in rows]
    if user["role"] == "nurse":
        return [user["department"]] if user["department"] else []
    if user["role"] in {"local_admin", "observer"}:
        building = user["building"]
        if not building:
            return [user["department"]] if user["department"] else []
        rows = conn.execute(
            "SELECT name FROM departments WHERE lower(building) = lower(?) ORDER BY name COLLATE NOCASE",
            (building,),
        ).fetchall()
        return [row["name"] for row in rows]
    return []


def ensure_department_in_scope(user: dict[str, Any], department: str) -> None:
    if department not in visible_departments(user):
        raise PermissionError("Bu bo'lim uchun ruxsat yo'q")


def user_data_scope_clause(
    conn: sqlite3.Connection,
    user: dict[str, Any],
    department_column: str = "department",
    created_by_column: str = "created_by",
    nurse_column: str | None = None,
) -> tuple[str, list[Any]]:
    if is_super_admin(user):
        return "1 = 1", []
    if user["role"] == "nurse":
        if nurse_column:
            return f"({created_by_column} = ? OR ({created_by_column} IS NULL AND lower({nurse_column}) = lower(?)))", [
                user["id"],
                user["full_name"],
            ]
        return f"{created_by_column} = ?", [user["id"]]
    if user["role"] in {"local_admin", "observer"}:
        departments = visible_departments_with_conn(conn, user)
        if not departments:
            return "1 = 0", []
        placeholders = ", ".join(["?"] * len(departments))
        return f"{department_column} IN ({placeholders})", departments
    return "1 = 0", []


def medicine_visible_to_user(conn: sqlite3.Connection, user: dict[str, Any], medicine: sqlite3.Row | dict[str, Any]) -> bool:
    if is_super_admin(user):
        return True
    if user["role"] == "nurse":
        return medicine["created_by"] == user["id"]
    if user["role"] in {"local_admin", "observer"}:
        return medicine["department"] in visible_departments_with_conn(conn, user)
    return False


def can_edit_building(user: dict[str, Any], row: sqlite3.Row | dict[str, Any]) -> bool:
    return is_super_admin(user)


def can_edit_department(user: dict[str, Any], row: sqlite3.Row | dict[str, Any]) -> bool:
    return is_super_admin(user)


def can_edit_medicine(user: dict[str, Any], row: sqlite3.Row | dict[str, Any]) -> bool:
    if is_super_admin(user):
        return True
    if user["role"] == "nurse":
        return row["created_by"] == user["id"]
    if user["role"] == "local_admin":
        return row["department"] in visible_departments(user)
    return False


def can_edit_entry(user: dict[str, Any], row: sqlite3.Row | dict[str, Any]) -> bool:
    if is_super_admin(user):
        return True
    if user["role"] == "nurse":
        return row["created_by"] == user["id"] or (not row["created_by"] and row["nurse_name"].lower() == user["full_name"].lower())
    if user["role"] == "local_admin":
        return row["department"] in visible_departments(user)
    return False


def scoped_department_clause(user: dict[str, Any], column: str = "department") -> tuple[str, list[Any]]:
    departments = visible_departments(user)
    if not departments:
        return "1 = 0", []
    placeholders = ", ".join(["?"] * len(departments))
    return f"{column} IN ({placeholders})", departments


def one_param(params: dict[str, list[str]], key: str) -> str:
    return params.get(key, [""])[0].strip()


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    created_at = now_iso()
    expires_at = (dt.datetime.now() + dt.timedelta(hours=SESSION_HOURS)).replace(microsecond=0).isoformat(sep=" ")
    with connect_db() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (created_at,))
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, created_at, expires_at),
        )
        conn.commit()
    return token, expires_at


def delete_session(token: str) -> None:
    with connect_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def create_captcha_challenge() -> dict[str, str]:
    left = secrets.randbelow(8) + 2
    right = secrets.randbelow(8) + 2
    token = secrets.token_urlsafe(24)
    question = f"{left} + {right} = ?"
    answer = str(left + right)
    created_at = now_iso()
    expires_at = (dt.datetime.now() + dt.timedelta(minutes=CAPTCHA_MINUTES)).replace(microsecond=0).isoformat(sep=" ")
    with connect_db() as conn:
        conn.execute("DELETE FROM captcha_challenges WHERE expires_at <= ?", (created_at,))
        conn.execute(
            """
            INSERT INTO captcha_challenges (token, question, answer, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token, question, answer, created_at, expires_at),
        )
        conn.commit()
    return {"token": token, "question": question}


def verify_captcha_challenge(token: str, answer: str) -> bool:
    token = token.strip()
    answer = answer.strip()
    if not token or not answer:
        return False
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT answer
            FROM captcha_challenges
            WHERE token = ?
              AND expires_at > ?
            """,
            (token, now_iso()),
        ).fetchone()
        conn.execute("DELETE FROM captcha_challenges WHERE token = ?", (token,))
        conn.execute("DELETE FROM captcha_challenges WHERE expires_at <= ?", (now_iso(),))
        conn.commit()
    if not row:
        return False
    return hmac.compare_digest(str(row["answer"]), answer)


def get_user_by_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
              AND sessions.expires_at > ?
              AND users.is_active = 1
            """,
            (token, now_iso()),
        ).fetchone()
    return dict(row) if row else None


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE lower(username) = lower(?)
              AND is_active = 1
            """,
            (username.strip(),),
        ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return dict(row)


def parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def session_cookie(token: str) -> str:
    max_age = SESSION_HOURS * 60 * 60
    return f"{SESSION_COOKIE}={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax"


def clear_session_cookie() -> str:
    return f"{SESSION_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if data.get("quantity") is not None:
        quantity = float(data["quantity"])
        data["quantity"] = int(quantity) if quantity.is_integer() else round(quantity, 3)
    return data


def entry_row_to_public(row: sqlite3.Row, user: dict[str, Any]) -> dict[str, Any]:
    data = row_to_dict(row)
    data["can_edit"] = can_edit_entry(user, row)
    return data


def build_entry_where(params: dict[str, list[str]], user: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    with connect_db() as conn:
        scope_sql, scope_values = user_data_scope_clause(conn, user, "department", "created_by", "nurse_name")
    clauses.append(scope_sql)
    values.extend(scope_values)

    date_from = one_param(params, "from")
    date_to = one_param(params, "to")
    q = one_param(params, "q")
    department = one_param(params, "department")

    if date_from:
        clauses.append("entry_date >= ?")
        values.append(date_from)
    if date_to:
        clauses.append("entry_date <= ?")
        values.append(date_to)
    if department:
        clauses.append("department = ?")
        values.append(department)
    if q:
        like = f"%{q}%"
        clauses.append(
            "("
            "patient_name LIKE ? OR patient_id LIKE ? OR department LIKE ? OR "
            "nurse_name LIKE ? OR medicine_name LIKE ? OR dose LIKE ? OR "
            "route LIKE ? OR prescription_no LIKE ? OR note LIKE ?"
            ")"
        )
        values.extend([like] * 9)

    return " WHERE " + " AND ".join(clauses), values


def build_medicine_where(params: dict[str, list[str]], user: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    with connect_db() as conn:
        scope_sql, scope_values = user_data_scope_clause(conn, user, "department", "created_by")
    clauses.append(scope_sql)
    values.extend(scope_values)

    q = one_param(params, "q")
    department = one_param(params, "department")
    only_available = one_param(params, "available")

    if department:
        clauses.append("department = ?")
        values.append(department)
    if only_available == "1":
        clauses.append("remaining_quantity > 0")
    if q:
        like = f"%{q}%"
        clauses.append("(name LIKE ? OR department LIKE ? OR form LIKE ? OR note LIKE ?)")
        values.extend([like] * 4)

    return " WHERE " + " AND ".join(clauses), values


def query_entries(params: dict[str, list[str]], user: dict[str, Any], limit: int | None = 1000) -> list[dict[str, Any]]:
    where_sql, values = build_entry_where(params, user)
    limit_sql = ""
    query_values = list(values)
    if limit is not None:
        limit_sql = "LIMIT ?"
        query_values.append(limit)
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM entries
            {where_sql}
            ORDER BY entry_date DESC, entry_time DESC, id DESC
            {limit_sql}
            """,
            query_values,
        ).fetchall()
    return [entry_row_to_public(row, user) for row in rows]


def query_medicines(params: dict[str, list[str]], user: dict[str, Any], limit: int | None = 1000) -> list[dict[str, Any]]:
    where_sql, values = build_medicine_where(params, user)
    limit_sql = ""
    query_values = list(values)
    if limit is not None:
        limit_sql = "LIMIT ?"
        query_values.append(limit)
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM medicines
            {where_sql}
            ORDER BY remaining_quantity > 0 DESC, name COLLATE NOCASE, received_date DESC, received_time DESC, id DESC
            {limit_sql}
            """,
            query_values,
        ).fetchall()
    return [medicine_row_to_public(row, user) for row in rows]


def parse_quantity(value: Any, label: str) -> float:
    raw = str(value).replace(",", ".").strip()
    try:
        number = float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} raqam bo'lishi kerak") from exc
    if number < 0:
        raise ValueError(f"{label} manfiy bo'lmasligi kerak")
    return number


def validate_date_time(date_value: str, time_value: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
        raise ValueError("Sana formati noto'g'ri")
    if not re.fullmatch(r"\d{2}:\d{2}", time_value):
        raise ValueError("Vaqt formati noto'g'ri")


def parse_medicine_payload(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not can_write(user):
        raise PermissionError("Ma'lumot kiritish huquqi yo'q")

    department = str(payload.get("department", "")).strip()
    name = str(payload.get("name", "")).strip()
    received_date = str(payload.get("received_date", "")).strip()
    received_time = str(payload.get("received_time", "")).strip()
    form = str(payload.get("form", "")).strip()
    note = str(payload.get("note", "")).strip()
    initial_quantity = parse_quantity(payload.get("initial_quantity", ""), "Qabul qilingan miqdor")
    remaining_quantity = parse_quantity(payload.get("remaining_quantity", initial_quantity), "Real qoldiq")

    if not department:
        raise ValueError("Bo'lim tanlanishi kerak")
    if not name:
        raise ValueError("Dori nomi kiritilishi kerak")
    if not form:
        raise ValueError("Dori shakli tanlanishi kerak")
    if initial_quantity <= 0:
        raise ValueError("Qabul qilingan miqdor 0 dan katta bo'lishi kerak")
    if remaining_quantity > initial_quantity:
        raise ValueError("Real qoldiq qabul qilingan miqdordan katta bo'lmasligi kerak")
    validate_date_time(received_date, received_time)
    ensure_department_in_scope(user, department)
    with connect_db() as conn:
        if not department_exists(conn, department):
            raise ValueError("Bo'lim ro'yxatdan tanlanishi kerak")

    return {
        "department": department,
        "name": name,
        "received_date": received_date,
        "received_time": received_time,
        "form": form,
        "initial_quantity": initial_quantity,
        "remaining_quantity": remaining_quantity,
        "note": note,
    }


def create_medicine(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not can_write(user):
        raise PermissionError("Dori kiritish uchun ruxsat yo'q")
    data = parse_medicine_payload(payload, user)
    now = now_iso()
    with connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO medicines (
                department, name, received_date, received_time, form,
                initial_quantity, remaining_quantity, note, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["department"],
                data["name"],
                data["received_date"],
                data["received_time"],
                data["form"],
                data["initial_quantity"],
                data["remaining_quantity"],
                data["note"],
                user["id"],
                now,
                now,
            ),
        )
        medicine_id = cursor.lastrowid
        log_action(conn, user, "Dori qabul qilindi", "medicine", medicine_id, data["name"])
        conn.commit()
        row = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    return medicine_row_to_public(row, user)


def update_medicine(medicine_id: int, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    data = parse_medicine_payload(payload, user)
    now = now_iso()
    with connect_db() as conn:
        old = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
        if not old:
            raise KeyError("Dori topilmadi")
        if not can_edit_medicine(user, old):
            raise PermissionError("Bu dorini tahrirlash uchun ruxsat yo'q")
        conn.execute(
            """
            UPDATE medicines
            SET department = ?,
                name = ?,
                received_date = ?,
                received_time = ?,
                form = ?,
                initial_quantity = ?,
                remaining_quantity = ?,
                note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                data["department"],
                data["name"],
                data["received_date"],
                data["received_time"],
                data["form"],
                data["initial_quantity"],
                data["remaining_quantity"],
                data["note"],
                now,
                medicine_id,
            ),
        )
        conn.execute(
            """
            UPDATE entries
            SET department = ?,
                medicine_name = ?,
                unit = ?,
                updated_at = ?
            WHERE medicine_id = ?
            """,
            (data["department"], data["name"], data["form"], now, medicine_id),
        )
        log_action(conn, user, "Dori tahrirlandi", "medicine", medicine_id, data["name"])
        conn.commit()
        row = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    return medicine_row_to_public(row, user)


def parse_entry_payload(payload: dict[str, Any], user: dict[str, Any], conn: sqlite3.Connection) -> dict[str, Any]:
    if not can_write(user):
        raise PermissionError("Ma'lumot kiritish huquqi yo'q")

    medicine_id_raw = str(payload.get("medicine_id", "")).strip()
    if not medicine_id_raw.isdigit():
        raise ValueError("Dori ro'yxatdan tanlanishi kerak")
    medicine_id = int(medicine_id_raw)
    medicine = conn.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    if not medicine:
        raise ValueError("Tanlangan dori topilmadi")
    if not medicine_visible_to_user(conn, user, medicine):
        raise PermissionError("Bu dori uchun ruxsat yo'q")
    ensure_department_in_scope(user, medicine["department"])

    entry_date = str(payload.get("entry_date", "")).strip()
    entry_time = str(payload.get("entry_time", "")).strip()
    patient_name = str(payload.get("patient_name", "")).strip()
    patient_id = str(payload.get("patient_id", "")).strip()
    nurse_name = str(payload.get("nurse_name", "")).strip()
    dose = str(payload.get("dose", "")).strip()
    route = str(payload.get("route", "")).strip()
    prescription_no = str(payload.get("prescription_no", "")).strip()
    note = str(payload.get("note", "")).strip()
    quantity = parse_quantity(payload.get("quantity", ""), "Ishlatilgan miqdor")

    if not patient_name:
        raise ValueError("Bemor F.I.Sh. kiritilishi kerak")
    if not nurse_name:
        raise ValueError("Hamshira F.I.Sh. kiritilishi kerak")
    if quantity <= 0:
        raise ValueError("Ishlatilgan miqdor 0 dan katta bo'lishi kerak")
    validate_date_time(entry_date, entry_time)

    return {
        "medicine_id": medicine_id,
        "entry_date": entry_date,
        "entry_time": entry_time,
        "patient_name": patient_name,
        "patient_id": patient_id,
        "department": medicine["department"],
        "nurse_name": nurse_name,
        "medicine_name": medicine["name"],
        "dose": dose,
        "quantity": quantity,
        "unit": medicine["form"],
        "route": route,
        "prescription_no": prescription_no,
        "note": note,
        "medicine": medicine,
    }


def create_entry(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not can_write(user):
        raise PermissionError("Sarf yozuvi kiritish uchun ruxsat yo'q")
    now = now_iso()
    with connect_db() as conn:
        data = parse_entry_payload(payload, user, conn)
        cursor = conn.execute(
            """
            UPDATE medicines
            SET remaining_quantity = remaining_quantity - ?, updated_at = ?
            WHERE id = ?
              AND remaining_quantity >= ?
            """,
            (data["quantity"], now, data["medicine_id"], data["quantity"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("Dori qoldig'i yetarli emas")
        columns = ENTRY_FIELDS + ["created_by", "created_at", "updated_at"]
        values = [data[field] for field in ENTRY_FIELDS] + [user["id"], now, now]
        placeholders = ", ".join(["?"] * len(columns))
        cursor = conn.execute(
            f"INSERT INTO entries ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        entry_id = cursor.lastrowid
        log_action(
            conn,
            user,
            "Dori sarfi saqlandi",
            "entry",
            entry_id,
            f"{data['patient_name']} - {data['medicine_name']} ({data['quantity']} {data['unit']})",
        )
        conn.commit()
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return entry_row_to_public(row, user)


def update_entry(entry_id: int, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    with connect_db() as conn:
        old = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if not old:
            raise KeyError("Yozuv topilmadi")
        if not can_edit_entry(user, old):
            raise PermissionError("Bu sarf yozuvini tahrirlash uchun ruxsat yo'q")
        data = parse_entry_payload(payload, user, conn)
        conn.execute(
            "UPDATE medicines SET remaining_quantity = remaining_quantity + ?, updated_at = ? WHERE id = ?",
            (old["quantity"], now, old["medicine_id"]),
        )
        cursor = conn.execute(
            """
            UPDATE medicines
            SET remaining_quantity = remaining_quantity - ?, updated_at = ?
            WHERE id = ?
              AND remaining_quantity >= ?
            """,
            (data["quantity"], now, data["medicine_id"], data["quantity"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("Dori qoldig'i yetarli emas")
        assignments = ", ".join([f"{field} = ?" for field in ENTRY_FIELDS] + ["updated_at = ?"])
        values = [data[field] for field in ENTRY_FIELDS] + [now, entry_id]
        conn.execute(f"UPDATE entries SET {assignments} WHERE id = ?", values)
        log_action(conn, user, "Dori sarfi yangilandi", "entry", entry_id, data["patient_name"])
        conn.commit()
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return entry_row_to_public(row, user)


def delete_entry(entry_id: int, user: dict[str, Any]) -> None:
    now = now_iso()
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            raise KeyError("Yozuv topilmadi")
        if not can_edit_entry(user, row):
            raise PermissionError("Bu sarf yozuvini o'chirish uchun ruxsat yo'q")
        if row["medicine_id"]:
            conn.execute(
                "UPDATE medicines SET remaining_quantity = remaining_quantity + ?, updated_at = ? WHERE id = ?",
                (row["quantity"], now, row["medicine_id"]),
            )
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        log_action(conn, user, "Dori sarfi o'chirildi", "entry", entry_id, row["patient_name"])
        conn.commit()


def get_stats(params: dict[str, list[str]], user: dict[str, Any]) -> dict[str, Any]:
    entry_where, entry_values = build_entry_where(params, user)
    med_where, med_values = build_medicine_where({}, user)
    with connect_db() as conn:
        totals = conn.execute(
            f"""
            SELECT
                COUNT(*) AS entry_count,
                COUNT(DISTINCT patient_name) AS patient_count,
                COUNT(DISTINCT medicine_name) AS used_medicine_count,
                COALESCE(SUM(quantity), 0) AS total_used
            FROM entries
            {entry_where}
            """,
            entry_values,
        ).fetchone()
        stock_totals = conn.execute(
            f"""
            SELECT
                COUNT(*) AS stock_batches,
                COALESCE(SUM(remaining_quantity), 0) AS total_remaining,
                SUM(CASE WHEN remaining_quantity <= 0 THEN 1 ELSE 0 END) AS empty_batches,
                SUM(CASE WHEN remaining_quantity > 0 AND remaining_quantity <= initial_quantity * 0.1 THEN 1 ELSE 0 END) AS low_batches
            FROM medicines
            {med_where}
            """,
            med_values,
        ).fetchone()
        by_medicine = conn.execute(
            f"""
            SELECT medicine_name, unit, COUNT(*) AS uses, SUM(quantity) AS total_quantity
            FROM entries
            {entry_where}
            GROUP BY medicine_name, unit
            ORDER BY total_quantity DESC, medicine_name ASC
            LIMIT 12
            """,
            entry_values,
        ).fetchall()
        by_department = conn.execute(
            f"""
            SELECT
                filtered.department,
                COALESCE(departments.building, '') AS building,
                COUNT(*) AS uses,
                SUM(filtered.quantity) AS total_quantity
            FROM (
                SELECT *
                FROM entries
                {entry_where}
            ) AS filtered
            LEFT JOIN departments ON lower(departments.name) = lower(filtered.department)
            GROUP BY filtered.department, departments.building
            ORDER BY uses DESC, filtered.department ASC
            LIMIT 12
            """,
            entry_values,
        ).fetchall()
        low_stock = conn.execute(
            f"""
            SELECT *
            FROM medicines
            {med_where}
              AND remaining_quantity <= initial_quantity * 0.1
            ORDER BY remaining_quantity ASC, name COLLATE NOCASE
            LIMIT 12
            """,
            med_values,
        ).fetchall()
        stock_by_department = conn.execute(
            f"""
            SELECT department, COUNT(*) AS batches, SUM(remaining_quantity) AS remaining_quantity
            FROM medicines
            {med_where}
            GROUP BY department
            ORDER BY department COLLATE NOCASE
            LIMIT 20
            """,
            med_values,
        ).fetchall()

    total_used = float(totals["total_used"] or 0)
    total_remaining = float(stock_totals["total_remaining"] or 0)
    return {
        "totals": {
            "entry_count": totals["entry_count"] or 0,
            "patient_count": totals["patient_count"] or 0,
            "used_medicine_count": totals["used_medicine_count"] or 0,
            "total_used": int(total_used) if total_used.is_integer() else round(total_used, 2),
            "stock_batches": stock_totals["stock_batches"] or 0,
            "total_remaining": int(total_remaining) if total_remaining.is_integer() else round(total_remaining, 2),
            "empty_batches": stock_totals["empty_batches"] or 0,
            "low_batches": stock_totals["low_batches"] or 0,
        },
        "by_medicine": [row_to_dict(row) for row in by_medicine],
        "by_department": [row_to_dict(row) for row in by_department],
        "low_stock": [medicine_to_public(row) for row in low_stock],
        "stock_by_department": [row_to_dict(row) for row in stock_by_department],
    }


def get_options(user: dict[str, Any]) -> dict[str, Any]:
    departments = visible_departments(user)
    with connect_db() as conn:
        if is_super_admin(user):
            buildings = [
                row["name"]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM buildings
                    ORDER BY name COLLATE NOCASE
                    """
                ).fetchall()
            ]
        else:
            assigned_building = user["building"] or department_building(conn, user["department"])
            buildings = [assigned_building] if assigned_building else []
        medicine_scope_sql, medicine_scope_values = user_data_scope_clause(conn, user, "department", "created_by")
        names = [
            row["value"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT name AS value
                FROM medicines
                WHERE {medicine_scope_sql}
                ORDER BY name COLLATE NOCASE
                LIMIT 300
                """,
                medicine_scope_values,
            ).fetchall()
        ]
        entry_scope_sql, entry_scope_values = user_data_scope_clause(conn, user, "department", "created_by", "nurse_name")
        routes = [
            row["value"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT route AS value
                FROM entries
                WHERE {entry_scope_sql}
                  AND route != ''
                ORDER BY route COLLATE NOCASE
                LIMIT 100
                """,
                entry_scope_values,
            ).fetchall()
        ]
    return {
        "departments": departments,
        "buildings": buildings,
        "forms": MEDICINE_FORMS,
        "medicine_names": names,
        "routes": routes,
    }


def list_buildings(user: dict[str, Any]) -> list[dict[str, Any]]:
    with connect_db() as conn:
        if is_super_admin(user):
            rows = conn.execute("SELECT * FROM buildings ORDER BY name COLLATE NOCASE").fetchall()
        elif user.get("building"):
            rows = conn.execute(
                "SELECT * FROM buildings WHERE lower(name) = lower(?) ORDER BY name COLLATE NOCASE",
                (user["building"],),
            ).fetchall()
        else:
            rows = []
    buildings = []
    for row in rows:
        data = building_to_public(row)
        data["can_edit"] = can_edit_building(user, row)
        buildings.append(data)
    return buildings


def list_departments(user: dict[str, Any]) -> list[dict[str, Any]]:
    with connect_db() as conn:
        if is_super_admin(user):
            rows = conn.execute("SELECT * FROM departments ORDER BY name COLLATE NOCASE").fetchall()
        else:
            departments = visible_departments_with_conn(conn, user)
            if not departments:
                return []
            placeholders = ", ".join(["?"] * len(departments))
            rows = conn.execute(
                f"SELECT * FROM departments WHERE name IN ({placeholders}) ORDER BY name COLLATE NOCASE",
                departments,
            ).fetchall()
    departments_public = []
    for row in rows:
        data = department_to_public(row)
        data["can_edit"] = can_edit_department(user, row)
        departments_public.append(data)
    return departments_public


def validate_new_building(payload: dict[str, Any]) -> dict[str, str]:
    name = str(payload.get("name", "")).strip()
    note = str(payload.get("note", "")).strip()
    if not name:
        raise ValueError("Korpus nomi kiritilishi kerak")
    if len(name) > 120:
        raise ValueError("Korpus nomi juda uzun")
    if len(note) > 500:
        raise ValueError("Izoh juda uzun")
    return {"name": name, "note": note}


def create_building(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not can_manage_departments(user):
        raise PermissionError("Korpus yaratish uchun super admin huquqi kerak")
    data = validate_new_building(payload)
    now = now_iso()
    try:
        with connect_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO buildings (name, note, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (data["name"], data["note"], now, now),
            )
            building_id = cursor.lastrowid
            log_action(conn, user, "Korpus yaratildi", "building", building_id, data["name"])
            conn.commit()
            row = conn.execute("SELECT * FROM buildings WHERE id = ?", (building_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu korpus allaqachon mavjud") from exc
    data_public = building_to_public(row)
    data_public["can_edit"] = can_edit_building(user, row)
    return data_public


def update_building(building_id: int, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not can_manage_departments(user):
        raise PermissionError("Korpusni tahrirlash uchun super admin huquqi kerak")
    data = validate_new_building(payload)
    now = now_iso()
    try:
        with connect_db() as conn:
            old = conn.execute("SELECT * FROM buildings WHERE id = ?", (building_id,)).fetchone()
            if not old:
                raise KeyError("Korpus topilmadi")
            old_name = old["name"]
            conn.execute(
                """
                UPDATE buildings
                SET name = ?,
                    note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (data["name"], data["note"], now, building_id),
            )
            conn.execute("UPDATE departments SET building = ?, updated_at = ? WHERE lower(building) = lower(?)", (data["name"], now, old_name))
            conn.execute("UPDATE users SET building = ?, updated_at = ? WHERE lower(building) = lower(?)", (data["name"], now, old_name))
            log_action(conn, user, "Korpus tahrirlandi", "building", building_id, data["name"])
            conn.commit()
            row = conn.execute("SELECT * FROM buildings WHERE id = ?", (building_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu korpus allaqachon mavjud") from exc
    data_public = building_to_public(row)
    data_public["can_edit"] = can_edit_building(user, row)
    return data_public


def validate_new_department(payload: dict[str, Any]) -> dict[str, str]:
    name = str(payload.get("name", "")).strip()
    building = str(payload.get("building", "")).strip()
    note = str(payload.get("note", "")).strip()
    if not name:
        raise ValueError("Bo'lim nomi kiritilishi kerak")
    if not building:
        raise ValueError("Korpus kiritilishi kerak")
    if len(name) > 120 or len(building) > 120:
        raise ValueError("Bo'lim yoki korpus nomi juda uzun")
    if len(note) > 500:
        raise ValueError("Izoh juda uzun")
    return {"name": name, "building": building, "note": note}


def create_department(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not is_super_admin(user):
        raise PermissionError("Bo'lim yaratish uchun super admin huquqi kerak")
    data = validate_new_department(payload)
    now = now_iso()
    try:
        with connect_db() as conn:
            if not building_exists(conn, data["building"]):
                raise ValueError("Avval korpusni ma'lumotnomaga qo'shing")
            cursor = conn.execute(
                """
                INSERT INTO departments (name, building, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (data["name"], data["building"], data["note"], now, now),
            )
            department_id = cursor.lastrowid
            log_action(conn, user, "Bo'lim yaratildi", "department", department_id, data["name"])
            conn.commit()
            row = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu bo'lim allaqachon mavjud") from exc
    data_public = department_to_public(row)
    data_public["can_edit"] = can_edit_department(user, row)
    return data_public


def update_department(department_id: int, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    if not can_manage_departments(user):
        raise PermissionError("Bo'limni tahrirlash uchun super admin huquqi kerak")
    data = validate_new_department(payload)
    now = now_iso()
    try:
        with connect_db() as conn:
            old = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
            if not old:
                raise KeyError("Bo'lim topilmadi")
            if not building_exists(conn, data["building"]):
                raise ValueError("Avval korpusni ma'lumotnomaga qo'shing")
            old_name = old["name"]
            conn.execute(
                """
                UPDATE departments
                SET name = ?,
                    building = ?,
                    note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (data["name"], data["building"], data["note"], now, department_id),
            )
            conn.execute("UPDATE medicines SET department = ?, updated_at = ? WHERE lower(department) = lower(?)", (data["name"], now, old_name))
            conn.execute("UPDATE entries SET department = ?, updated_at = ? WHERE lower(department) = lower(?)", (data["name"], now, old_name))
            conn.execute("UPDATE users SET department = ?, building = ?, updated_at = ? WHERE lower(department) = lower(?)", (data["name"], data["building"], now, old_name))
            log_action(conn, user, "Bo'lim tahrirlandi", "department", department_id, data["name"])
            conn.commit()
            row = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu bo'lim allaqachon mavjud") from exc
    data_public = department_to_public(row)
    data_public["can_edit"] = can_edit_department(user, row)
    return data_public


def department_building(conn: sqlite3.Connection, department: str) -> str:
    row = conn.execute("SELECT building FROM departments WHERE lower(name) = lower(?)", (department,)).fetchone()
    return row["building"] if row else ""


def can_edit_user(actor: dict[str, Any], target: sqlite3.Row | dict[str, Any]) -> bool:
    if target["role"] == "super_admin":
        return False
    if is_super_admin(actor):
        return True
    return (
        actor["role"] == "local_admin"
        and target["role"] in {"nurse", "observer"}
        and bool(actor["building"])
        and target["building"].lower() == actor["building"].lower()
    )


def parse_active_flag(value: Any, default: bool = True) -> int:
    if value is None or value == "":
        return 1 if default else 0
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "on", "faol"} else 0


def validate_user_payload(
    payload: dict[str, Any],
    actor: dict[str, Any],
    conn: sqlite3.Connection,
    existing: sqlite3.Row | None = None,
) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    full_name = str(payload.get("full_name", "")).strip()
    role = str(payload.get("role", "")).strip()
    department = str(payload.get("department", "")).strip()
    building = str(payload.get("building", "")).strip()
    password = str(payload.get("password", ""))
    active_default = bool(existing["is_active"]) if existing else True
    is_active = parse_active_flag(payload.get("is_active"), active_default)

    if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", username):
        raise ValueError("Login 3-40 belgi bo'lishi, faqat harf, raqam, nuqta, _ yoki - ishlatilishi kerak")
    if not full_name:
        raise ValueError("F.I.Sh. kiritilishi kerak")
    if role not in role_options_for(actor):
        raise ValueError("Rol noto'g'ri tanlangan")

    if actor["role"] == "local_admin":
        if not actor["building"]:
            raise PermissionError("Local admin uchun korpus biriktirilmagan")
        building = actor["building"]
        if role == "nurse":
            if not department:
                raise ValueError("Hamshira uchun bo'lim tanlanishi kerak")
            if department not in visible_departments_with_conn(conn, actor):
                raise PermissionError("Bu bo'lim uchun ruxsat yo'q")
        else:
            department = ""

    if role == "nurse" and not department:
        raise ValueError("Hamshira uchun bo'lim tanlanishi kerak")
    if role in {"local_admin", "observer"} and not building:
        raise ValueError("Local admin yoki kuzatuvchi uchun korpus tanlanishi kerak")
    if password and len(password) < 6:
        raise ValueError("Parol kamida 6 belgidan iborat bo'lishi kerak")
    if not existing and len(password) < 6:
        raise ValueError("Parol kamida 6 belgidan iborat bo'lishi kerak")
    if department and not department_exists(conn, department):
        raise ValueError("Avval bo'limni ma'lumotnomaga qo'shing")
    if role == "nurse" and not building:
        building = department_building(conn, department)
    if building:
        if not building_exists(conn, building):
            raise ValueError("Korpus bo'limlar ro'yxatida mavjud emas")
    return {
        "username": username,
        "full_name": full_name,
        "role": role,
        "department": department if role == "nurse" else "",
        "building": building,
        "password": password,
        "is_active": is_active,
    }


def create_user(payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    try:
        with connect_db() as conn:
            data = validate_user_payload(payload, actor, conn)
            cursor = conn.execute(
                """
                INSERT INTO users (
                    username, full_name, password_hash, role, department, building,
                    created_by, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["username"],
                    data["full_name"],
                    hash_password(data["password"]),
                    data["role"],
                    data["department"],
                    data["building"],
                    actor["id"],
                    data["is_active"],
                    now,
                    now,
                ),
            )
            user_id = cursor.lastrowid
            log_action(conn, actor, "Foydalanuvchi yaratildi", "user", user_id, data["username"])
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu login allaqachon mavjud") from exc
    return user_to_public(row)


def update_user(user_id: int, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    try:
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise KeyError("Foydalanuvchi topilmadi")
            if not can_edit_user(actor, row):
                raise PermissionError("Bu foydalanuvchini tahrirlash uchun ruxsat yo'q")
            data = validate_user_payload(payload, actor, conn, row)
            values: list[Any] = [
                data["username"],
                data["full_name"],
                data["role"],
                data["department"],
                data["building"],
                data["is_active"],
                now,
            ]
            password_sql = ""
            if data["password"]:
                password_sql = ", password_hash = ?"
                values.append(hash_password(data["password"]))
            values.append(user_id)
            conn.execute(
                f"""
                UPDATE users
                SET username = ?,
                    full_name = ?,
                    role = ?,
                    department = ?,
                    building = ?,
                    is_active = ?,
                    updated_at = ?
                    {password_sql}
                WHERE id = ?
                """,
                values,
            )
            log_action(conn, actor, "Foydalanuvchi yangilandi", "user", user_id, data["username"])
            conn.commit()
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu login allaqachon mavjud") from exc
    return user_to_public(updated)


def list_users(user: dict[str, Any]) -> list[dict[str, Any]]:
    with connect_db() as conn:
        if is_super_admin(user):
            rows = conn.execute(
                """
                SELECT *
                FROM users
                ORDER BY role = 'super_admin' DESC, building COLLATE NOCASE, department COLLATE NOCASE, full_name COLLATE NOCASE
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM users
                WHERE role != 'super_admin'
                  AND lower(building) = lower(?)
                ORDER BY building COLLATE NOCASE, department COLLATE NOCASE, full_name COLLATE NOCASE
                """,
                (user["building"],),
            ).fetchall()
    users = []
    for row in rows:
        data = user_to_public(row)
        data["can_edit"] = can_edit_user(user, row)
        users.append(data)
    return users


def managed_user_ids(conn: sqlite3.Connection, user: dict[str, Any]) -> list[int]:
    if is_super_admin(user):
        rows = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
        return [int(row["id"]) for row in rows]
    rows = conn.execute(
        """
        SELECT id
        FROM users
        WHERE role != 'super_admin'
          AND lower(building) = lower(?)
        ORDER BY id
        """,
        (user["building"],),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def logs_to_public(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for row in rows:
        logs.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
                "role_label": role_label(row["role"]),
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "description": row["description"],
                "created_at": row["created_at"],
            }
        )
    return logs


def get_admin_activity(user: dict[str, Any]) -> dict[str, Any]:
    if not can_manage_users(user):
        raise PermissionError("Bu ma'lumotlar adminlar uchun")
    with connect_db() as conn:
        ids = managed_user_ids(conn, user)
        if not ids:
            return {"user_stats": [], "logs": [], "totals": {"users": 0, "active_users": 0, "entries": 0, "logs": 0}}
        placeholders = ", ".join(["?"] * len(ids))
        users = conn.execute(
            f"""
            SELECT *
            FROM users
            WHERE id IN ({placeholders})
            ORDER BY role = 'super_admin' DESC, building COLLATE NOCASE, department COLLATE NOCASE, full_name COLLATE NOCASE
            """,
            ids,
        ).fetchall()
        user_stats: list[dict[str, Any]] = []
        total_entries = 0
        total_logs = 0
        active_users = 0
        for row in users:
            entry_stats = conn.execute(
                """
                SELECT COUNT(*) AS entries, COALESCE(SUM(quantity), 0) AS total_quantity, MAX(created_at) AS last_entry
                FROM entries
                WHERE created_by = ?
                   OR lower(nurse_name) = lower(?)
                """,
                (row["id"], row["full_name"]),
            ).fetchone()
            medicine_stats = conn.execute(
                "SELECT COUNT(*) AS medicines, MAX(created_at) AS last_medicine FROM medicines WHERE created_by = ?",
                (row["id"],),
            ).fetchone()
            log_stats = conn.execute(
                "SELECT COUNT(*) AS logs, MAX(created_at) AS last_log FROM audit_logs WHERE user_id = ?",
                (row["id"],),
            ).fetchone()
            entries = int(entry_stats["entries"] or 0)
            logs = int(log_stats["logs"] or 0)
            total_entries += entries
            total_logs += logs
            if row["is_active"]:
                active_users += 1
            total_quantity = float(entry_stats["total_quantity"] or 0)
            last_seen = max(
                [value for value in (entry_stats["last_entry"], medicine_stats["last_medicine"], log_stats["last_log"]) if value],
                default="",
            )
            user_stats.append(
                {
                    **user_to_public(row),
                    "entry_count": entries,
                    "total_quantity": int(total_quantity) if total_quantity.is_integer() else round(total_quantity, 2),
                    "medicine_count": int(medicine_stats["medicines"] or 0),
                    "log_count": logs,
                    "last_activity": last_seen,
                }
            )
        logs = conn.execute(
            f"""
            SELECT *
            FROM audit_logs
            WHERE user_id IN ({placeholders})
            ORDER BY created_at DESC, id DESC
            LIMIT 200
            """,
            ids,
        ).fetchall()
    return {
        "user_stats": user_stats,
        "logs": logs_to_public(logs),
        "totals": {
            "users": len(user_stats),
            "active_users": active_users,
            "entries": total_entries,
            "logs": total_logs,
        },
    }


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xlsx_cell(value: Any, row: int, col: int, style: int | None = None) -> str:
    ref = f"{column_name(col)}{row}"
    style_attr = f' s="{style}"' if style is not None else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = xml_escape(str(value), quote=False)
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>'


def build_sheet(rows: list[list[Any]], widths: list[int]) -> str:
    col_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate(widths, start=1)
    )
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        style = 1 if row_index == 1 else None
        cells = "".join(xlsx_cell(value, row_index, col_index, style) for col_index, value in enumerate(row, start=1))
        row_xml.append(f'<row r="{row_index}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{col_xml}</cols>"
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        "</worksheet>"
    )


def make_xlsx(params: dict[str, list[str]], user: dict[str, Any]) -> bytes:
    entries = query_entries(params, user, limit=None)
    medicines = query_medicines(params, user, limit=None)
    stats = get_stats(params, user)

    journal_rows: list[list[Any]] = [XLSX_HEADERS]
    for item in entries:
        journal_rows.append(
            [
                item["id"],
                item["entry_date"],
                item["entry_time"],
                item["patient_name"],
                item["patient_id"],
                item["department"],
                item["nurse_name"],
                item["medicine_name"],
                item["dose"],
                item["quantity"],
                item["unit"],
                item["route"],
                item["prescription_no"],
                item["note"],
                item["created_at"],
            ]
        )

    medicine_rows: list[list[Any]] = [MEDICINE_XLSX_HEADERS]
    for item in medicines:
        medicine_rows.append(
            [
                item["id"],
                item["department"],
                item["name"],
                item["received_date"],
                item["received_time"],
                item["form"],
                item["initial_quantity"],
                item["remaining_quantity"],
                item["note"],
            ]
        )

    stat_rows: list[list[Any]] = [
        ["Ko'rsatkich", "Qiymat"],
        ["Sarf yozuvlari", stats["totals"]["entry_count"]],
        ["Bemorlar soni", stats["totals"]["patient_count"]],
        ["Ishlatilgan dori turlari", stats["totals"]["used_medicine_count"]],
        ["Jami ishlatilgan miqdor", stats["totals"]["total_used"]],
        ["Dori partiyalari", stats["totals"]["stock_batches"]],
        ["Jami qoldiq", stats["totals"]["total_remaining"]],
        ["Kam qolgan partiyalar", stats["totals"]["low_batches"]],
        ["Tugagan partiyalar", stats["totals"]["empty_batches"]],
        [],
        ["Dori nomi", "Shakli", "Ishlatish soni", "Jami sarf"],
    ]
    for row in stats["by_medicine"]:
        stat_rows.append([row["medicine_name"], row["unit"], row["uses"], row["total_quantity"]])
    stat_rows.append([])
    stat_rows.append(["Bo'lim", "Korpus", "Yozuvlar soni", "Jami sarf"])
    for row in stats["by_department"]:
        stat_rows.append([row["department"], row["building"], row["uses"], row["total_quantity"]])

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Sarf jurnali" sheetId="1" r:id="rId1"/>
<sheet name="Dorilar qoldig'i" sheetId="2" r:id="rId2"/>
<sheet name="Statistika" sheetId="3" r:id="rId3"/>
</sheets>
</workbook>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF25636B"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>""",
        )
        zf.writestr("xl/worksheets/sheet1.xml", build_sheet(journal_rows, [8, 12, 10, 26, 14, 20, 22, 24, 14, 12, 12, 18, 18, 32, 20]))
        zf.writestr("xl/worksheets/sheet2.xml", build_sheet(medicine_rows, [8, 20, 24, 16, 12, 12, 16, 14, 32]))
        zf.writestr("xl/worksheets/sheet3.xml", build_sheet(stat_rows, [32, 18, 18, 18]))
        created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        zf.writestr(
            "docProps/core.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Dori-darmon jurnali</dc:title>
<dc:creator>Elektron jurnal</dc:creator>
<cp:lastModifiedBy>Elektron jurnal</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>""",
        )
        zf.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Elektron jurnal</Application>
</Properties>""",
        )
    return buffer.getvalue()


def safe_static_path(path: str) -> Path | None:
    path = unquote(path)
    if path == "/" or path == "/index.html":
        return STATIC_DIR / "index.html"
    if not path.startswith("/static/"):
        return None
    relative = path.removeprefix("/static/")
    candidate = (STATIC_DIR / relative).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    return candidate


class JournalHandler(BaseHTTPRequestHandler):
    server_version = "MedicationJournal/3.0"

    def log_message(self, format: str, *args: Any) -> None:
        if sys.stderr:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def send_json(self, status: int, data: Any, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_problem(self, status: int, message: str) -> None:
        self.send_json(status, {"error": message})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("JSON formati noto'g'ri") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON obyekt bo'lishi kerak")
        return payload

    def session_token(self) -> str | None:
        return parse_cookie_header(self.headers.get("Cookie")).get(SESSION_COOKIE)

    def current_user(self) -> dict[str, Any] | None:
        return get_user_by_session(self.session_token())

    def require_user(self) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            self.send_problem(401, "Tizimga kiring")
            return None
        return user

    def require_super_admin(self) -> dict[str, Any] | None:
        user = self.require_user()
        if not user:
            return None
        if not is_super_admin(user):
            self.send_problem(403, "Bu amal uchun super admin huquqi kerak")
            return None
        return user

    def require_user_manager(self) -> dict[str, Any] | None:
        user = self.require_user()
        if not user:
            return None
        if not can_manage_users(user):
            self.send_problem(403, "Foydalanuvchilarni boshqarish uchun admin huquqi kerak")
            return None
        return user

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/me":
            user = self.current_user()
            self.send_json(
                200,
                {
                    "authenticated": bool(user),
                    "user": user_to_public(user) if user else None,
                    "roles": role_options_for(user) if user else {},
                    "permissions": permissions_for(user) if user else {},
                },
            )
            return
        if parsed.path == "/api/captcha":
            self.send_json(200, {"captcha": create_captcha_challenge()})
            return

        if parsed.path == "/api/users":
            user = self.require_user_manager()
            if not user:
                return
            self.send_json(200, {"users": list_users(user), "roles": role_options_for(user)})
            return

        if parsed.path == "/api/admin/activity":
            user = self.require_user_manager()
            if not user:
                return
            try:
                self.send_json(200, get_admin_activity(user))
            except PermissionError as exc:
                self.send_problem(403, str(exc))
            return

        if parsed.path == "/api/departments":
            user = self.require_user()
            if not user:
                return
            self.send_json(200, {"departments": list_departments(user)})
            return

        if parsed.path == "/api/buildings":
            user = self.require_user()
            if not user:
                return
            self.send_json(200, {"buildings": list_buildings(user)})
            return

        if parsed.path == "/api/medicines":
            user = self.require_user()
            if not user:
                return
            self.send_json(200, {"medicines": query_medicines(params, user)})
            return

        if parsed.path in {"/api/entries", "/api/stats", "/api/options", "/export.xlsx"}:
            user = self.require_user()
            if not user:
                return
            if parsed.path == "/api/entries":
                self.send_json(200, {"entries": query_entries(params, user)})
                return
            if parsed.path == "/api/stats":
                self.send_json(200, get_stats(params, user))
                return
            if parsed.path == "/api/options":
                self.send_json(200, get_options(user))
                return
            content = make_xlsx(params, user)
            filename = f"dori-darmon-monitoring-{dt.date.today().isoformat()}.xlsx"
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        static_path = safe_static_path(parsed.path)
        if static_path and static_path.exists() and static_path.is_file():
            content = static_path.read_bytes()
            mime = "text/html" if static_path.suffix == ".html" else "text/plain"
            if static_path.suffix == ".css":
                mime = "text/css"
            elif static_path.suffix == ".js":
                mime = "application/javascript"
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_problem(404, "Sahifa topilmadi")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/login":
            try:
                payload = self.read_json()
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            if not verify_captcha_challenge(str(payload.get("captcha_token", "")), str(payload.get("captcha_answer", ""))):
                self.send_problem(400, "Captcha noto'g'ri yoki muddati tugagan")
                return
            user = authenticate_user(str(payload.get("username", "")), str(payload.get("password", "")))
            if not user:
                self.send_problem(401, "Login yoki parol noto'g'ri")
                return
            token, _ = create_session(int(user["id"]))
            with connect_db() as conn:
                log_action(conn, user, "Tizimga kirdi", "session", None, user["username"])
                conn.commit()
            self.send_json(
                200,
                {
                    "authenticated": True,
                    "user": user_to_public(user),
                    "roles": role_options_for(user),
                    "permissions": permissions_for(user),
                },
                {"Set-Cookie": session_cookie(token)},
            )
            return

        if parsed.path == "/api/logout":
            user = self.current_user()
            token = self.session_token()
            if token:
                delete_session(token)
            if user:
                with connect_db() as conn:
                    log_action(conn, user, "Tizimdan chiqdi", "session", None, user["username"])
                    conn.commit()
            self.send_json(200, {"ok": True}, {"Set-Cookie": clear_session_cookie()})
            return

        if parsed.path == "/api/users":
            user = self.require_user_manager()
            if not user:
                return
            try:
                payload = self.read_json()
                created_user = create_user(payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            self.send_json(201, {"user": created_user})
            return

        if parsed.path == "/api/departments":
            user = self.require_super_admin()
            if not user:
                return
            try:
                payload = self.read_json()
                department = create_department(payload, user)
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            self.send_json(201, {"department": department})
            return

        if parsed.path == "/api/buildings":
            user = self.require_super_admin()
            if not user:
                return
            try:
                payload = self.read_json()
                building = create_building(payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            self.send_json(201, {"building": building})
            return

        if parsed.path == "/api/medicines":
            user = self.require_user()
            if not user:
                return
            try:
                payload = self.read_json()
                medicine = create_medicine(payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            self.send_json(201, {"medicine": medicine})
            return

        if parsed.path == "/api/entries":
            user = self.require_user()
            if not user:
                return
            try:
                payload = self.read_json()
                entry = create_entry(payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            self.send_json(201, {"entry": entry})
            return

        self.send_problem(404, "Endpoint topilmadi")

    def do_PUT(self) -> None:
        building_match = re.fullmatch(r"/api/buildings/(\d+)", urlparse(self.path).path)
        if building_match:
            user = self.require_super_admin()
            if not user:
                return
            try:
                payload = self.read_json()
                building = update_building(int(building_match.group(1)), payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            except KeyError as exc:
                self.send_problem(404, str(exc))
                return
            self.send_json(200, {"building": building})
            return

        department_match = re.fullmatch(r"/api/departments/(\d+)", urlparse(self.path).path)
        if department_match:
            user = self.require_super_admin()
            if not user:
                return
            try:
                payload = self.read_json()
                department = update_department(int(department_match.group(1)), payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            except KeyError as exc:
                self.send_problem(404, str(exc))
                return
            self.send_json(200, {"department": department})
            return

        medicine_match = re.fullmatch(r"/api/medicines/(\d+)", urlparse(self.path).path)
        if medicine_match:
            user = self.require_user()
            if not user:
                return
            try:
                payload = self.read_json()
                medicine = update_medicine(int(medicine_match.group(1)), payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            except KeyError as exc:
                self.send_problem(404, str(exc))
                return
            self.send_json(200, {"medicine": medicine})
            return

        user_match = re.fullmatch(r"/api/users/(\d+)", urlparse(self.path).path)
        if user_match:
            user = self.require_user_manager()
            if not user:
                return
            try:
                payload = self.read_json()
                updated_user = update_user(int(user_match.group(1)), payload, user)
            except PermissionError as exc:
                self.send_problem(403, str(exc))
                return
            except ValueError as exc:
                self.send_problem(400, str(exc))
                return
            except KeyError as exc:
                self.send_problem(404, str(exc))
                return
            self.send_json(200, {"user": updated_user})
            return

        match = re.fullmatch(r"/api/entries/(\d+)", urlparse(self.path).path)
        if not match:
            self.send_problem(404, "Endpoint topilmadi")
            return
        user = self.require_user()
        if not user:
            return
        try:
            payload = self.read_json()
            entry = update_entry(int(match.group(1)), payload, user)
        except PermissionError as exc:
            self.send_problem(403, str(exc))
            return
        except ValueError as exc:
            self.send_problem(400, str(exc))
            return
        except KeyError as exc:
            self.send_problem(404, str(exc))
            return
        self.send_json(200, {"entry": entry})

    def do_DELETE(self) -> None:
        match = re.fullmatch(r"/api/entries/(\d+)", urlparse(self.path).path)
        if not match:
            self.send_problem(404, "Endpoint topilmadi")
            return
        user = self.require_user()
        if not user:
            return
        try:
            delete_entry(int(match.group(1)), user)
        except PermissionError as exc:
            self.send_problem(403, str(exc))
            return
        except KeyError as exc:
            self.send_problem(404, str(exc))
            return
        self.send_json(200, {"ok": True})


def main() -> None:
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), JournalHandler)
    if sys.stdout:
        print(f"Elektron jurnal ishga tushdi: http://127.0.0.1:{port}", flush=True)
        print(f"Boshlang'ich super admin: {DEFAULT_SUPER_USERNAME} / {DEFAULT_SUPER_PASSWORD}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if sys.stdout:
            print("\nServer to'xtatildi")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        DATA_DIR.mkdir(exist_ok=True)
        with (DATA_DIR / "server-error.log").open("a", encoding="utf-8") as log_file:
            log_file.write(f"\n[{now_iso()}]\n")
            traceback.print_exc(file=log_file)
        raise
