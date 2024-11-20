"""A module containing useful parsing functions."""

from typing import Literal


def str_to_num(
    num_str: str | None, cast_to: Literal["int", "float"]
) -> int | float | None:
    """Return either a numeric representation of the string or None."""
    number = None
    if num_str:
        try:
            if cast_to == "float":
                number = float(num_str)
            elif cast_to == "int":
                number = int(float(num_str))
        except ValueError:
            pass
    return number
