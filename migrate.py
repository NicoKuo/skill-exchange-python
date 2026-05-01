"""Safe schema migration for the local SQLite database.

This script only adds missing columns and updates existing rows. It does not
drop tables or reseed data.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from pathlib import Path


TARGET_EMAIL = 'admin.gmail.com'
TARGET_NAME = '系統管理者'
TARGET_PASSWORD = '123456'
TARGET_ROLE = 'super_admin'


def _default_db_path() -> Path:
    candidates = []

    database_url = os.getenv('DATABASE_URL', '')
    if database_url.startswith('sqlite:///'):
        candidates.append(Path(database_url.replace('sqlite:///', '', 1)))

    candidates.extend([
        Path('instance') / 'skill_exchange_test5.db',
        Path('instance') / 'skill_exchange.db',
        Path('skill_exchange.db'),
    ])

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def _generate_password_hash(password: str) -> str:
    try:
        from werkzeug.security import generate_password_hash

        return generate_password_hash(password)
    except Exception:
        salt = secrets.token_hex(8)
        iterations = 600000
        derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
        return f'pbkdf2:sha256:{iterations}${salt}${derived.hex()}'


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    cursor.execute(f'PRAGMA table_info({table_name})')
    return {row[1] for row in cursor.fetchall()}


def _ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_sql: str) -> bool:
    columns = _table_columns(cursor, table_name)
    if column_name in columns:
        return False
    cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_sql}')
    return True


def run_migration(database_path: Path) -> None:
    if not database_path.exists():
        raise FileNotFoundError(f'找不到資料庫檔案: {database_path}')

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = {row['name'] for row in cursor.fetchall()}

        if 'users' in table_names:
            user_columns = _table_columns(cursor, 'users')
            if 'role' not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
                user_columns = _table_columns(cursor, 'users')

            if 'role' in user_columns:
                cursor.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR role = '' OR role = 'student'")

            cursor.execute('SELECT id, name, email, role, bio, password_hash FROM users WHERE email = ?', (TARGET_EMAIL,))
            admin_row = cursor.fetchone()

            if admin_row is None:
                cursor.execute(
                    'INSERT INTO users (name, email, password_hash, role, bio) VALUES (?, ?, ?, ?, ?)',
                    (TARGET_NAME, TARGET_EMAIL, _generate_password_hash(TARGET_PASSWORD), TARGET_ROLE, '最高管理者'),
                )
            else:
                cursor.execute(
                    "UPDATE users SET role = ?, name = COALESCE(NULLIF(name, ''), ?), bio = COALESCE(NULLIF(bio, ''), ?) WHERE email = ?",
                    (TARGET_ROLE, TARGET_NAME, '最高管理者', TARGET_EMAIL),
                )

        if 'skills' in table_names:
            _ensure_column(cursor, 'skills', 'is_active', 'is_active BOOLEAN NOT NULL DEFAULT 1')
            cursor.execute("UPDATE skills SET is_active = 1 WHERE is_active IS NULL")

        for table_name in ('messages', 'chat_messages'):
            if table_name in table_names:
                _ensure_column(cursor, table_name, 'file_url', 'file_url VARCHAR(255)')
                _ensure_column(cursor, table_name, 'file_name', 'file_name VARCHAR(255)')
                _ensure_column(cursor, table_name, 'file_type', 'file_type VARCHAR(30)')

        connection.commit()

        verification_cursor = connection.cursor()
        verification_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        verification_tables = {row['name'] for row in verification_cursor.fetchall()}

        if 'users' in verification_tables:
            user_columns = _table_columns(verification_cursor, 'users')
            if 'role' not in user_columns:
                raise RuntimeError('users 資料表仍缺少 role 欄位')

        if 'skills' in verification_tables:
            skill_columns = _table_columns(verification_cursor, 'skills')
            if 'is_active' not in skill_columns:
                raise RuntimeError('skills 資料表仍缺少 is_active 欄位')

        for table_name in ('messages', 'chat_messages'):
            if table_name in verification_tables:
                message_columns = _table_columns(verification_cursor, table_name)
                missing = {'file_url', 'file_name', 'file_type'} - message_columns
                if missing:
                    missing_list = ', '.join(sorted(missing))
                    raise RuntimeError(f'{table_name} 資料表仍缺少欄位: {missing_list}')

    finally:
        connection.close()


def main() -> None:
    database_path = _default_db_path()
    run_migration(database_path)
    print(f'資料庫 schema 檢查與修補完成: {database_path}')


if __name__ == '__main__':
    main()