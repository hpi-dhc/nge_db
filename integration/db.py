"""A module that handles connection to the DB."""

import logging
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def ensure_local_db_exists(db_url: str) -> None:
    """Create the local DB if it does not yet exist."""
    if db_url.startswith("sqlite"):
        db_path = Path(db_url.split("///")[-1])
        if not db_path.exists():
            logger.info(f"Local sqlite DB not found at {db_path}, creating it")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(db_path)
            connection.close()
        else:
            logger.info(f"Local sqlite DB found at {db_path}")
    else:
        pass


def get_engine(db_url: str, echo : bool = False, **engine_kwargs) -> Engine:
    """Return a connection to the DB specified by db_url."""
    if db_url.startswith("sqlite"):
        ensure_local_db_exists(db_url)
    engine = create_engine(db_url, future=True, echo=echo, **engine_kwargs)
    return engine
