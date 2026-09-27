"""Exit codes and user-facing failures shared by every command.

User-facing errors are raised as `fail("...")`: the message is printed to
stderr prefixed with "reins: " and the process exits 1. Never print a Python
traceback to the user for an expected condition.
"""

import sys

OK = 0
ERROR = 1  # usage error, broken input, or unavailable capability
WARN = 2   # gate: warnings only
BLOCK = 3  # gate: at least one un-waived BLOCK


def fail(message: str):
    raise SystemExit("reins: " + message)


def unavailable(capability: str) -> int:
    """Report a capability that is declared but not implemented yet.

    The controller skill treats this as "该能力不可用" and stops."""
    sys.stderr.write("reins: %s 尚未实现（该能力不可用）\n" % capability)
    return ERROR
