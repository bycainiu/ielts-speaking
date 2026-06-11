from __future__ import annotations

from typing import Any


def load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("PostgreSQL persistence requires psycopg[binary]") from exc
    return psycopg, Jsonb
