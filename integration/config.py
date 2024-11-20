"""A module for loading the project configuration."""

from configparser import ConfigParser, BasicInterpolation
from pathlib import Path
import os

class EnvInterpolation(BasicInterpolation):
    """Interpolation which expands environment variables in values."""

    def before_get(self, parser, section, option, value, defaults):
        value = super().before_get(parser, section, option, value, defaults)
        return os.path.expandvars(value)

def load_config(path: str | Path = "config.ini") -> ConfigParser:
    """Load the project configuration."""
    config = ConfigParser(interpolation=EnvInterpolation())
    config.read_file(open(path))
    return config


def parse_config_list(cfg_value: str | list[str]) -> list[str]:
    """Parse a comma-separated list field string from the config file to a Python list."""
    out: list[str] = []
    if isinstance(cfg_value, str):
        if cfg_value.strip() == "None":
            out = []
        else:
            out = cfg_value.split(",")
    elif isinstance(cfg_value, list):
        out = cfg_value
    return out
