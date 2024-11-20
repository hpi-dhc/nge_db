"""A module containing helpful functions for queries module."""

import datetime

from sqlalchemy import DateTime, Integer, Select
from sqlalchemy.orm import InstrumentedAttribute


def apply_limit(query: Select, limit: int | None):
    """Return a Select statement with applied limit."""
    if limit is not None:
        if limit > 0:
            query = query.limit(limit)
    return query


def apply_year_filter(
    query: Select,
    year_min: int | None,
    year_max: int | None,
    year_col: InstrumentedAttribute,
):
    """Return a Select statement with applied year filter."""
    if year_min is not None:
        if year_min > 0:
            if isinstance(year_col.type, DateTime):
                query = query.where(year_col >= datetime.date(year_min, 1, 1))
            elif isinstance(year_col.type, Integer):
                query = query.where(year_col >= year_min)
    if year_max is not None:
        if year_max > 0:
            if isinstance(year_col.type, DateTime):
                query = query.where(year_col <= datetime.date(year_max, 12, 31))
            elif isinstance(year_col.type, Integer):
                query = query.where(year_col <= year_max)
    return query
