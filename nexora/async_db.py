"""aiosqlite worker with our explicit backend connector (no global patching)."""
import aiosqlite
from sqlite3 import Row, IntegrityError, OperationalError
from nexora.db import connect as sync_connect


def connect(database, *, iter_chunk_size=64, **kwargs):
    return aiosqlite.Connection(
        lambda: sync_connect(database, **kwargs), iter_chunk_size=iter_chunk_size
    )
