"""Safe schema migration for SQLite and PostgreSQL.

This script only adds missing columns and updates existing rows. It does not
drop tables or reseed data.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
DEFAULT_SQLITE_URLS = (
    'sqlite:///instance/skill_exchange_test5.db',
    'sqlite:///instance/skill_exchange.db',
    'sqlite:///skill_exchange.db',
)
BASE_DIR = Path(__file__).resolve().parent


def _normalize_database_url(database_url: str) -> str:
    database_url = database_url.strip()
    if database_url.startswith('postgres://'):
        return 'postgresql://' + database_url[len('postgres://'):]
    return database_url


def _resolve_database_url() -> str:
    database_url = _normalize_database_url(os.getenv('DATABASE_URL', ''))
    if database_url:
        return database_url

    for candidate in DEFAULT_SQLITE_URLS:
        sqlite_path = (BASE_DIR / candidate.replace('sqlite:///', '', 1)).resolve()
        if sqlite_path.exists():
            return f'sqlite:///{sqlite_path.as_posix()}'

    instance_dir = BASE_DIR / 'instance'
    if instance_dir.exists():
        db_candidates = sorted(
            instance_dir.glob('skill_exchange*.db'),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if db_candidates:
            return f'sqlite:///{db_candidates[0].resolve().as_posix()}'

    root_candidates = sorted(
        BASE_DIR.glob('skill_exchange*.db'),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if root_candidates:
        return f'sqlite:///{root_candidates[0].resolve().as_posix()}'

    return DEFAULT_SQLITE_URLS[0]


def _connect(database_url: str):
    if database_url.startswith('sqlite:///'):
        sqlite_path = Path(database_url.replace('sqlite:///', '', 1))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection, 'sqlite'

    if database_url.startswith('postgresql://'):
        try:
            import psycopg2
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                'PostgreSQL migration needs psycopg2. Install project dependencies first.'
            ) from exc

        connection = psycopg2.connect(database_url)
        return connection, 'postgresql'

    raise RuntimeError(f'Unsupported DATABASE_URL: {database_url}')


def _table_names(cursor, dialect_name: str) -> set[str]:
    if dialect_name == 'sqlite':
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
    )
    return {row[0] for row in cursor.fetchall()}


def _table_columns(cursor, table_name: str, dialect_name: str) -> set[str]:
    if dialect_name == 'sqlite':
        cursor.execute(f'PRAGMA table_info({table_name})')
        return {row[1] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        (table_name,),
    )
    return {row[0] for row in cursor.fetchall()}


def _add_column_sql(dialect_name: str, table_name: str, column_name: str) -> str:
    if column_name == 'role':
        return f"ALTER TABLE {table_name} ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"

    if column_name == 'status':
        return f"ALTER TABLE {table_name} ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"

    if column_name == 'is_active':
        default_value = 'true' if dialect_name == 'postgresql' else '1'
        return f"ALTER TABLE {table_name} ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT {default_value}"

    if column_name in {'file_url', 'file_name'}:
        return f"ALTER TABLE {table_name} ADD COLUMN {column_name} VARCHAR(255)"

    if column_name == 'file_type':
        return f"ALTER TABLE {table_name} ADD COLUMN file_type VARCHAR(30)"

    raise ValueError(f'Unsupported column: {column_name}')


def _ensure_column(cursor, connection, table_name: str, column_name: str, dialect_name: str) -> bool:
    columns = _table_columns(cursor, table_name, dialect_name)
    if column_name in columns:
        return False
    cursor.execute(_add_column_sql(dialect_name, table_name, column_name))
    connection.commit()
    return True
def run_migration(database_url: str | None = None) -> None:
    resolved_url = _normalize_database_url(database_url or _resolve_database_url())
    connection, dialect_name = _connect(resolved_url)

    try:
        cursor = connection.cursor()
        table_names = _table_names(cursor, dialect_name)

        if 'users' in table_names:
            _ensure_column(cursor, connection, 'users', 'role', dialect_name)
            _ensure_column(cursor, connection, 'users', 'status', dialect_name)
            cursor.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR role = '' OR role = 'student'")
            if dialect_name == 'sqlite':
                cursor.execute("UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''")
            else:
                cursor.execute("UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''")
            connection.commit()

        if 'skills' in table_names:
            _ensure_column(cursor, connection, 'skills', 'is_active', dialect_name)
            if dialect_name == 'sqlite':
                cursor.execute('UPDATE skills SET is_active = 1 WHERE is_active IS NULL')
            else:
                cursor.execute('UPDATE skills SET is_active = true WHERE is_active IS NULL')
            connection.commit()

        for table_name in ('messages', 'chat_messages'):
            if table_name in table_names:
                _ensure_column(cursor, connection, table_name, 'file_url', dialect_name)
                _ensure_column(cursor, connection, table_name, 'file_name', dialect_name)
                _ensure_column(cursor, connection, table_name, 'file_type', dialect_name)

        verification_tables = _table_names(cursor, dialect_name)

        if 'users' in verification_tables:
            user_columns = _table_columns(cursor, 'users', dialect_name)
            if 'role' not in user_columns:
                raise RuntimeError('users 資料表仍缺少 role 欄位')
            if 'status' not in user_columns:
                raise RuntimeError('users 資料表仍缺少 status 欄位')

        if 'skills' in verification_tables:
            skill_columns = _table_columns(cursor, 'skills', dialect_name)
            if 'is_active' not in skill_columns:
                raise RuntimeError('skills 資料表仍缺少 is_active 欄位')

        for table_name in ('messages', 'chat_messages'):
            if table_name in verification_tables:
                message_columns = _table_columns(cursor, table_name, dialect_name)
                missing = {'file_url', 'file_name', 'file_type'} - message_columns
                if missing:
                    missing_list = ', '.join(sorted(missing))
                    raise RuntimeError(f'{table_name} 資料表仍缺少欄位: {missing_list}')

        connection.commit()
    finally:
        connection.close()


def main() -> None:
    database_url = _resolve_database_url()
    run_migration(database_url)
    print(f'資料庫 schema 檢查與修補完成: {database_url}')


if __name__ == '__main__':
    main()