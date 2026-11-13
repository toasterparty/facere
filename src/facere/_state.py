"""The state: a record of each rule's last success, or of the inputs that changed during its last execution, and the hash cache, kept in a SQLite database in the output directory.

The database is open only while it is read or written, so a task may delete the output directory on any OS. A database Facere can't read counts as empty, which costs only rebuilds, while one it can't write raises OSError. Writes skip fsync: a write lost to a crash costs a rebuild, since the next invocation re-verifies every output.
"""

import contextlib
import os
import sqlite3
from collections.abc import Generator
from typing import Any, NamedTuple

from facere._cache import Entry, HashChanges

_SCHEMA_VERSION = 5
_TABLES = ("records", "listing", "declared", "moved", "hashes")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (outputs TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, output_hashes TEXT NOT NULL, added_inputs TEXT NOT NULL, added_names TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS listing (id INTEGER PRIMARY KEY CHECK (id = 0), paths TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS declared (id INTEGER PRIMARY KEY CHECK (id = 0), outputs TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS moved (outputs TEXT PRIMARY KEY, paths TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS hashes (path TEXT PRIMARY KEY, stamp TEXT NOT NULL, digest TEXT NOT NULL, is_racy INTEGER NOT NULL) WITHOUT ROWID;
"""
_SEPARATOR = "\0"


class Record(NamedTuple):
    """A rule's last success. `added_inputs` pairs each input its recipe reported with that input's hash, and `added_names` holds the path key of the file name of each one reported, those outside the root included."""

    fingerprint: str
    output_hashes: tuple[str, ...]
    added_inputs: tuple[tuple[str, str], ...]
    added_names: tuple[str, ...]


class State(NamedTuple):
    """Everything load reads. `moved` holds, for each rule left unrecorded by its last execution, the inputs that changed during it. `declared` holds the output keys save_declared last saved, or None where it saved none, and `listing` the files save_listing last saved, read only where a record holds a file name a new file could shadow."""

    records: dict[tuple[str, ...], Record]
    moved: dict[tuple[str, ...], tuple[str, ...]]
    declared: frozenset[str] | None
    listing: frozenset[str]
    hashes: dict[str, Entry]


def calc_key(outputs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(outputs))


def has_added_names(records: dict[tuple[str, ...], Record]) -> bool:
    """Say whether any record holds a file name a new file could shadow, which alone makes the tree's listing worth keeping."""
    return any(record.added_names for record in records.values())


def load(path: str) -> State:
    """Return the state, or an empty one where it is missing, unreadable, or of another schema."""
    empty = State({}, {}, None, frozenset(), {})
    if not os.path.exists(path):
        return empty
    try:
        with contextlib.closing(sqlite3.connect(path)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                return empty
            return _read(connection)
    except sqlite3.DatabaseError:
        return empty


def save(path: str, key: tuple[str, ...], record: Record, changes: HashChanges) -> None:
    """Record the success of the rule outputting `key`, forgetting what save_moved kept of it, and save the hash cache's `changes`."""
    with _open(path) as connection:
        connection.execute("DELETE FROM moved WHERE outputs = ?", (_SEPARATOR.join(key),))
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
        _write_hashes(connection, changes)


def remove(path: str, keys: list[tuple[str, ...]]) -> None:
    """Forget everything kept of the rules outputting `keys`."""
    if not keys or not os.path.exists(path):
        return
    joined = [(_SEPARATOR.join(key),) for key in keys]
    with _open(path) as connection:
        connection.executemany("DELETE FROM records WHERE outputs = ?", joined)
        connection.executemany("DELETE FROM moved WHERE outputs = ?", joined)


def save_moved(
    path: str, key: tuple[str, ...], paths: tuple[str, ...], changes: HashChanges
) -> None:
    """Keep the inputs `paths` that changed while the rule outputting `key` executed, which left it unrecorded, and save the hash cache's `changes`."""
    with _open(path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO moved VALUES (?, ?)",
            (_SEPARATOR.join(key), _SEPARATOR.join(paths)),
        )
        _write_hashes(connection, changes)


def save_hashes(path: str, changes: HashChanges) -> None:
    """Save the hash cache's `changes`, unless the state is gone, as after a task deleted the output directory."""
    if not os.path.exists(path) or not (changes.saved or changes.removed):
        return
    with _open(path) as connection:
        _write_hashes(connection, changes)


def save_listing(path: str, listing: frozenset[str]) -> None:
    """Replace the saved listing, unless the state is gone."""
    _save_paths(path, "INSERT OR REPLACE INTO listing VALUES (0, ?)", listing)


def save_declared(path: str, outputs: frozenset[str]) -> None:
    """Replace the saved output keys, unless the state is gone."""
    _save_paths(path, "INSERT OR REPLACE INTO declared VALUES (0, ?)", outputs)


def _read(connection: sqlite3.Connection) -> State:
    records = {
        _split(outputs): Record(fingerprint, _split(hashes), _pair(_split(added)), _split(names))
        for outputs, fingerprint, hashes, added, names in _fetch(
            connection,
            "SELECT outputs, fingerprint, output_hashes, added_inputs, added_names FROM records",
        )
    }
    moved = {
        _split(outputs): _split(paths)
        for outputs, paths in _fetch(connection, "SELECT outputs, paths FROM moved")
    }
    declared = _read_paths(connection, "SELECT outputs FROM declared")
    is_listed = has_added_names(records)
    listing = _read_paths(connection, "SELECT paths FROM listing") if is_listed else None
    hashes = {
        path: Entry(stamp, digest, bool(is_racy))
        for path, stamp, digest, is_racy in _fetch(
            connection, "SELECT path, stamp, digest, is_racy FROM hashes"
        )
    }
    return State(records, moved, declared, listing or frozenset(), hashes)


def _read_paths(connection: sqlite3.Connection, query: str) -> frozenset[str] | None:
    rows = _fetch(connection, query)
    return frozenset(_split(rows[0][0])) if rows else None


def _fetch(connection: sqlite3.Connection, query: str) -> list[Any]:
    return connection.execute(query).fetchall()


def _write_hashes(connection: sqlite3.Connection, changes: HashChanges) -> None:
    connection.executemany(
        "DELETE FROM hashes WHERE path = ?", [(path,) for path in changes.removed]
    )
    connection.executemany(
        "INSERT OR REPLACE INTO hashes VALUES (?, ?, ?, ?)",
        [
            (path, entry.stamp, entry.digest, int(entry.is_racy))
            for path, entry in changes.saved.items()
        ],
    )


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
        connection.execute("PRAGMA synchronous = OFF")
        if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
            drops = "".join(f"DROP TABLE IF EXISTS {table}; " for table in _TABLES)
            connection.executescript(f"{drops}{_SCHEMA} PRAGMA user_version = {_SCHEMA_VERSION};")
        else:
            connection.executescript(_SCHEMA)
    except BaseException:
        connection.close()
        raise
    return connection
