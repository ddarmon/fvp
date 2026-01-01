"""FVP algorithm helpers (pure functions, no I/O)."""

import random
from typing import List, Optional, Tuple

from .models import Task


def first_live_index(tasks: List[Task]) -> Optional[int]:
    """Return the 1-based index of the first non-done task, or None."""
    for i, t in enumerate(tasks, start=1):
        if t.status != "done":
            return i
    return None


def last_dotted_index(tasks: List[Task]) -> Optional[int]:
    """Return the 1-based index of the lowest dotted task, or None."""
    idx = None
    for i, t in enumerate(tasks, start=1):
        if t.status == "dotted":
            idx = i
    return idx


def previous_dotted_above(tasks: List[Task], index: int) -> Optional[int]:
    """Find the nearest dotted task strictly above index, or None."""
    for i in range(index - 1, 0, -1):
        if tasks[i - 1].status == "dotted":
            return i
    return None


def clear_all_dots(tasks: List[Task]) -> None:
    """Reset all dotted tasks to open status."""
    for t in tasks:
        if t.status == "dotted":
            t.status = "open"


def finish_effects_after_action(
    tasks: List[Task], acted_index: int
) -> Tuple[Optional[int], bool]:
    """Post-action bookkeeping after done/stop.

    If there is no dotted item above acted_index, we completed the root:
    clear all dots and reset last_did.

    Returns (new_last_did, root_cleared).
    """
    prev_dot = previous_dotted_above(tasks, acted_index)
    if prev_dot is None:
        clear_all_dots(tasks)
        return None, True
    return acted_index, False


def ensure_root_dotted(tasks: List[Task]) -> Optional[int]:
    """Ensure the root task is dotted; return its index or None if no live tasks."""
    ridx = first_live_index(tasks)
    if ridx is None:
        return None
    if tasks[ridx - 1].status != "dotted":
        tasks[ridx - 1].status = "dotted"
    return ridx


def shuffle_tasks(tasks: List[Task]) -> None:
    """Shuffle live tasks in-place; done tasks moved to end, dots cleared."""
    live = [t for t in tasks if t.status != "done"]
    done = [t for t in tasks if t.status == "done"]
    random.shuffle(live)
    tasks.clear()
    tasks.extend(live + done)
    clear_all_dots(tasks)
