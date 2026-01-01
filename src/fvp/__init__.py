"""FVP - Final Version Perfected task management."""

__version__ = "1.0.0"

from .models import Task, DEFAULT_DIR, DEFAULT_LIST, list_path
from .storage import read_file, write_file, get_available_lists
from .core import (
    first_live_index,
    last_dotted_index,
    previous_dotted_above,
    clear_all_dots,
    finish_effects_after_action,
    shuffle_tasks,
)

__all__ = [
    "Task",
    "DEFAULT_DIR",
    "DEFAULT_LIST",
    "list_path",
    "read_file",
    "write_file",
    "get_available_lists",
    "first_live_index",
    "last_dotted_index",
    "previous_dotted_above",
    "clear_all_dots",
    "finish_effects_after_action",
    "shuffle_tasks",
]
