"""Hook policies (design doc §2.4, §6.6). Owner: T0 (chain); policy modules: T6.

hook.py normalizes the platform payload into an event dict (see hook.normalize)
and runs the chains below. Each policy is a module with one function:

  PRE_TOOL policies:  def pre_tool(ev: dict) -> Optional[str]   # block reason, or None to allow
  PROMPT policies:    def prompt(ev: dict) -> Optional[str]     # note shown to the model, or None

Rules for every policy:
  - Pure decision from `ev` plus files on disk; no network, no git writes.
  - Must return within ~1 s: hooks run on every tool call.
  - An exception is logged by the chain and treated as allow (a broken hook must
    never lock the user out); layers 1 and 2 (CLI, git hooks) still hold.
  - Block reasons are one Chinese sentence telling the model what to do instead.
"""

from importlib import import_module

PRE_TOOL = ["probe", "spec_gate", "bash_guard"]
PROMPT = ["waive_grant", "gate_router"]


def _run(names, fn, ev, errors):
    for name in names:
        try:
            yield name, getattr(import_module("%s.%s" % (__name__, name)), fn)(ev)
        except NotImplementedError:
            continue
        except Exception as e:  # noqa: BLE001 - see module docstring
            errors.append("%s: %r" % (name, e))


def pre_tool(ev: dict, errors: list):
    """First block reason from the PRE_TOOL chain, or None."""
    for _, reason in _run(PRE_TOOL, "pre_tool", ev, errors):
        if reason:
            return reason
    return None


def prompt(ev: dict, errors: list):
    """Notes from the PROMPT chain joined, or None."""
    notes = [n for _, n in _run(PROMPT, "prompt", ev, errors) if n]
    return "\n".join(notes) or None
