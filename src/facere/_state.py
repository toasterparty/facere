"""The state: a record of each rule's last success, kept in a SQLite database in the output directory.

The database is open only while it is read or written, so a task may delete the output directory on any OS. A database Facere can't read counts as empty, which costs only rebuilds, while one it can't write raises OSError.
"""

import contextlib
import os
import sqlite3
from collections.abc import Generator
from typing import NamedTuple

_SCHEMA_VERSION = 3
_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (outputs TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, output_hashes TEXT NOT NULL, added_inputs TEXT NOT NULL, added_names TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS listing (id INTEGER PRIMARY KEY CHECK (id = 0), paths TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS declared (id INTEGER PRIMARY KEY CHECK (id = 0), outputs TEXT NOT NULL);
"""
_SEPARATOR = "\0"


class Record(NamedTuple):
    """A rule's last success. `added_inputs` pairs each input its recipe reported with that input's hash, and `added_names` holds the path key of the file name of each one reported, those outside the root included."""

    fingerprint: str
    output_hashes: tuple[str, ...]
    added_inputs: tuple[tuple[str, str], ...]
    added_names: tuple[str, ...]


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
                "SELECT outputs, fingerprint, output_hashes, added_inputs, added_names FROM records"
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return {
        _split(outputs): Record(fingerprint, _split(hashes), _pair(_split(added)), _split(names))
        for outputs, fingerprint, hashes, added, names in rows
    }


def save(path: str, key: tuple[str, ...], record: Record) -> None:
    with _open(path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?)",
            (
                _SEPARATOR.join(key),
                record.fingerprint,
                _SEPARATOR.join(record.output_hashes),
                _SEPARATOR.join(item for pair in record.added_inputs for item in pair),
                _SEPARATOR.join(record.added_names),
            ),
        )


def remove(path: str, keys: list[tuple[str, ...]]) -> None:
    if not keys or not os.path.exists(path):
        return
    with _open(path) as connection:
        connection.executemany(
            "DELETE FROM records WHERE outputs = ?", [(_SEPARATOR.join(key),) for key in keys]
        )


def load_listing(path: str) -> frozenset[str]:
    """Return the files save_listing last saved, or none where it saved none."""
    return _load_paths(path, "SELECT paths FROM listing") or frozenset()


def save_listing(path: str, listing: frozenset[str]) -> None:
    """Replace the saved listing, unless the state is gone, as after a task deleted the output directory."""
    _save_paths(path, "INSERT OR REPLACE INTO listing VALUES (0, ?)", listing)


def load_declared(path: str) -> frozenset[str] | None:
    """Return the output keys save_declared last saved, or None where it saved none."""
    return _load_paths(path, "SELECT outputs FROM declared")


def save_declared(path: str, outputs: frozenset[str]) -> None:
    """Replace the saved output keys, unless the state is gone."""
    _save_paths(path, "INSERT OR REPLACE INTO declared VALUES (0, ?)", outputs)


def _load_paths(path: str, query: str) -> frozenset[str] | None:
    if not os.path.exists(path):
        return None
    try:
        with contextlib.closing(sqlite3.connect(path)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                return None
            row = connection.execute(query).fetchone()
    except sqlite3.DatabaseError:
        return None
    return frozenset(_split(row[0])) if row else None


def _save_paths(path: str, statement: str, paths: frozenset[str]) -> None:
    if not os.path.exists(path):
        return
    with _open(path) as connection:
        connection.execute(statement, (_SEPARATOR.join(sorted(paths)),))


def _split(text: str) -> tuple[str, ...]:
    return tuple(text.split(_SEPARATOR)) if text else ()


def _pair(items: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(zip(items[::2], items[1::2], strict=True))


@contextlib.contextmanager
def _open(path: str) -> Generator[sqlite3.Connection]:
    """Yield a connection that commits when the block succeeds, raising OSError when SQLite fails."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        try:
            connection = _connect(path)
        except sqlite3.DatabaseError:
            os.remove(path)
            connection = _connect(path)
        with contextlib.closing(connection), connection:
            yield connection
    except sqlite3.Error as error:
        raise OSError(f"{path}: {error}") from error


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
            connection.executescript(
                f"DROP TABLE IF EXISTS records; DROP TABLE IF EXISTS listing; DROP TABLE IF EXISTS declared; {_SCHEMA} PRAGMA user_version = {_SCHEMA_VERSION};"
            )
        else:
            connection.executescript(_SCHEMA)
    except BaseException:
        connection.close()
        raise
    return connection
