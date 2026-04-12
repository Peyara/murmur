"""DuckDB read-only connection manager for the API server."""

from contextlib import asynccontextmanager
from pathlib import Path

import duckdb
from fastapi import FastAPI, Request


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open a read-only DuckDB connection at startup, close on shutdown."""
    db_path = app.state.db_path
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    app.state.db = duckdb.connect(str(db_path), read_only=True)
    yield
    app.state.db.close()


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    """FastAPI dependency — returns a cursor for thread-safe concurrent reads."""
    return request.app.state.db.cursor()
