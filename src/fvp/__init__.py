"""FVP - Final Version Perfected task management."""

__version__ = "1.0.0"

from .models import Task, DEFAULT_PATH
from .storage import read_file, write_file
from .core import (
    first_live_index,
    last_dotted_index,
    previous_dotted_above,
    clear_all_dots,
    finish_effects_after_action,
)

__all__ = [
    "Task",
    "DEFAULT_PATH",
    "read_file",
    "write_file",
    "first_live_index",
    "last_dotted_index",
    "previous_dotted_above",
    "clear_all_dots",
    "finish_effects_after_action",
]
