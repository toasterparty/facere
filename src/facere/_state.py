"""The state: a record of each rule's last success, kept in a SQLite database in the output directory.

The database is open only while it is read or written, so a task may delete the output directory on any OS. A database Facere can't read counts as empty, which costs only rebuilds.
"""

import contextlib
import os
import sqlite3
from collections.abc import Generator
from typing import NamedTuple

_SCHEMA_VERSION = 1
_SCHEMA = "CREATE TABLE IF NOT EXISTS records (outputs TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, output_hashes TEXT NOT NULL) WITHOUT ROWID"
_SEPARATOR = "\0"


class Record(NamedTuple):
    fingerprint: str
    output_hashes: tuple[str, ...]


def calc_key(outputs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(outputs))


def load(path: str) -> dict[tuple[str, ...], Record]:
    if not os.path.exists(path):
        return {}
    try:
        with contextlib.closing(sqlite3.connect(path)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                return {}
            rows = connection.execute(
                "SELECT outputs, fingerprint, output_hashes FROM records"
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return {
        tuple(outputs.split(_SEPARATOR)): Record(fingerprint, tuple(hashes.split(_SEPARATOR)))
        for outputs, fingerprint, hashes in rows
    }


def save(path: str, key: tuple[str, ...], record: Record) -> None:
    with _open(path) as connection, connection:
        connection.execute(
            "INSERT OR REPLACE INTO records VALUES (?, ?, ?)",
            (_SEPARATOR.join(key), record.fingerprint, _SEPARATOR.join(record.output_hashes)),
        )


def remove(path: str, keys: list[tuple[str, ...]]) -> None:
    if not keys or not os.path.exists(path):
        return
    with _open(path) as connection, connection:
        connection.executemany(
            "DELETE FROM records WHERE outputs = ?", [(_SEPARATOR.join(key),) for key in keys]
        )


@contextlib.contextmanager
def _open(path: str) -> Generator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        connection = _connect(path)
    except sqlite3.DatabaseError:
        os.remove(path)
        connection = _connect(path)
    try:
        yield connection
    finally:
        connection.close()


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
            connection.executescript(
                f"DROP TABLE IF EXISTS records; {_SCHEMA}; PRAGMA user_version = {_SCHEMA_VERSION};"
            )
        else:
            connection.execute(_SCHEMA)
    except BaseException:
        connection.close()
        raise
    return connection
