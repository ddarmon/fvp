"""Data models and constants for FVP."""

import os
import re
from dataclasses import dataclass
from typing import Literal

DEFAULT_PATH = os.path.expanduser("~/.fvp.txt")

STATE_RE = re.compile(r"^#\s*FVP_STATE\s+last_did=(\-?\d+)\s*$")
TASK_RE = re.compile(r"^\s*\[(.?)\]\s*(.*\S)?\s*$")

TaskStatus = Literal["open", "dotted", "done"]


@dataclass
class Task:
    """A single FVP task with text and status."""

    text: str
    status: TaskStatus  # "open" | "dotted" | "done"
