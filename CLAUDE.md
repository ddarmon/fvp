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
# TUI (interactive) - shows picker if multiple lists exist
uv run fvp

# TUI with specific list
uv run fvp -l work
uv run fvp --list personal

# TUI with full path override (backwards compatible)
uv run fvp -f ~/custom/tasks.txt

# List all available task lists
uv run fvp lists

# CLI subcommands (use default list if -l not specified)
uv run fvp list
uv run fvp add "Task text"
uv run fvp next    # interactive scan
uv run fvp done 3
uv run fvp stop 3  # cross out and re-add at bottom

# CLI with specific list
uv run fvp -l work list
uv run fvp -l work add "Work task"
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

- **models.py**: `Task` dataclass, `DEFAULT_DIR`, `DEFAULT_LIST`, `list_path()`, `STATE_RE`, `TASK_RE`
- **core.py**: Pure FVP algorithm functions (no I/O)
  - `first_live_index()`, `last_dotted_index()`, `previous_dotted_above()`
  - `clear_all_dots()`, `finish_effects_after_action()`, `ensure_root_dotted()`
- **storage.py**: `read_file()`, `write_file()`, `append_to_archive()`, `ensure_file_exists()`, `get_available_lists()`
- **cli.py**: argparse setup, command handlers, `main()` entry point
- **tui.py**: `TUI` class with curses rendering, list picker, Strict Mode state machine
  - List picker: shown when multiple lists exist and no list specified
  - Strict Mode: minimal UI (just task text), algorithm invisible
  - Free Mode (press `M`): shows technical details for debugging

## Directory Structure

Task lists are stored in `~/.fvp/`:

```
~/.fvp/
├── default.fvp          # Default list
├── default.fvp.archive  # Archive for default list
├── work.fvp             # Custom list
├── work.fvp.archive
└── personal.fvp
```

## File Format

Plain-text `.fvp` files:

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
