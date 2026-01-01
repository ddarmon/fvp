"""Data models and constants for FVP."""

import os
import re
from dataclasses import dataclass
from typing import Literal

DEFAULT_DIR = os.path.expanduser("~/.fvp")
DEFAULT_LIST = "default"


def list_path(name: str) -> str:
    """Return the full path for a named list: ~/.fvp/{name}.fvp"""
    return os.path.join(DEFAULT_DIR, f"{name}.fvp")

STATE_RE = re.compile(r"^#\s*FVP_STATE\s+last_did=(\-?\d+)\s*$")
TASK_RE = re.compile(r"^\s*\[(.?)\]\s*(.*\S)?\s*$")

TaskStatus = Literal["open", "dotted", "done"]


@dataclass
class Task:
    """A single FVP task with text and status."""

    text: str
    status: TaskStatus  # "open" | "dotted" | "done"
