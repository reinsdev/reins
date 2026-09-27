"""CLI subcommands. Each module exposes:

    def register(sub) -> None     # add its parser to the argparse subparsers
    def run(a) -> int             # execute; return an errors.* exit code

cli.py imports every module listed in COMMANDS; a task only edits its own
command modules. Undone commands return errors.unavailable(<name>).
"""

# module name -> owner task (see docs/dev/tasks.md)
COMMANDS = {
    "version": "T0",
    "status": "T2",
    "resume": "T2",
    "new": "T2",
    "retry": "T2",
    "complexity": "T2",
    "design": "T2",
    "tasks_sync": "T2",
    "gate": "T0",
    "retro": "T6",
    "waive": "T6",
    "githook": "T6",
    "hook": "T0",
    "archive": "T7",
    "init_config": "T5",
}
