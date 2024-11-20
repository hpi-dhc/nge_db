"""A module for creating an Entity-Relation Diagram of the database."""

import argparse
import inspect
import pathlib

import eralchemy2
from sqlalchemy import Engine, MetaData
from sqlalchemy.orm import DeclarativeBase

from integration.config import load_config
from integration.db import get_engine

parser = argparse.ArgumentParser()
parser.add_argument(
    "-o",
    "--out",
    help="output path for the ER diagram",
    default="erd.png",
    type=str,
)


def create_erd(
    diagram_path: pathlib.Path | str,
    engine: Engine,
    orm_module: DeclarativeBase | None = None,
):
    """Write an entity-relation diagram to diagram_path."""
    meta = MetaData()
    meta.reflect(bind=engine)
    table_names = None
    if orm_module is not None:
        module = orm_module.__name__
        table_names = [
            t[1].__table__.name
            for t in inspect.getmembers(
                orm_module, lambda a: (inspect.isclass(a) and module == a.__module__)
            )
        ]
    eralchemy2.render_er(
        meta,
        str(diagram_path),
        include_tables=table_names,
    )


def main():
    """Parse path argument and create ER diagram."""
    db_url = load_config()["DB"]["url"]
    cfg = parser.parse_args()
    create_erd(diagram_path=cfg.out, engine=get_engine(db_url))


if __name__ == "__main__":
    main()
