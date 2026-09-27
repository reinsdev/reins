"""waive-grant: issue a one-time grant when the user's prompt is exactly a
confirmation phrase (grants.WAIVE_PHRASE / DOWNGRADE_PHRASE). Owner: T6.
Delegates to grants.issue_from_prompt()."""

from typing import Optional


def prompt(ev: dict) -> Optional[str]:
    raise NotImplementedError
