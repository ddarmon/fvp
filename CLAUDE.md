# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working
with code in this repository.

## Overview

FVP is a minimalist implementation of Mark Forster's "Final Version
Perfected" task management system. Single `fvp` command provides both
interactive TUI (default) and CLI subcommands.

No external dependencies---pure Python 3 with only standard library modules
(`curses`, `argparse`, `dataclasses`).

## Running with uv

```bash
# TUI (interactive, default)
uv run fvp
uv run fvp -f ~/mylist.txt

# CLI subcommands
uv run fvp list
uv run fvp add "Task text"
uv run fvp next    # interactive scan
uv run fvp done 3
uv run fvp stop 3  # cross out and re-add at bottom
```

## Package Structure

```
src/fvp/
├── __init__.py   # Version and exports
├── models.py     # Task dataclass, constants, regex
├── core.py       # FVP algorithm (pure functions)
├── storage.py    # File I/O, archive
├── cli.py        # argparse CLI, entry point
└── tui.py        # curses TUI
```

## Module Responsibilities

- **models.py**: `Task` dataclass, `DEFAULT_PATH`, `STATE_RE`, `TASK_RE`
- **core.py**: Pure FVP algorithm functions (no I/O)
  - `first_live_index()`, `last_dotted_index()`, `previous_dotted_above()`
  - `clear_all_dots()`, `finish_effects_after_action()`, `ensure_root_dotted()`
- **storage.py**: `read_file()`, `write_file()`, `append_to_archive()`, `ensure_file_exists()`
- **cli.py**: argparse setup, command handlers, `main()` entry point
- **tui.py**: `TUI` class with curses rendering, Strict Mode state machine
  - Strict Mode: minimal UI (just task text), algorithm invisible
  - Free Mode (press `M`): shows technical details for debugging

## File Format

Single plain-text file (default: `~/.fvp.txt`):

    # FVP_STATE last_did=5
    [ ] open task
    [.] dotted task
    [x] crossed-out task

## Key FVP Concepts

- **Root**: First live (non-crossed-out) task; always gets dotted at scan start
- **Benchmark**: Last dotted item above current position; used for pairwise comparison
- **Scan**: Walk down list asking "want this more than benchmark?" -> dot if yes
- **Do now**: Lowest dotted task
- **Stop early**: Cross out and re-add same text at bottom (preserves momentum)
