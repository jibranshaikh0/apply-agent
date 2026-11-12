"""Stop-before-submit guard, enforced in code, not in prompts.

Any browser action that targets an element whose text looks like a final
submission MUST go through assert_not_submit() first. The agent presents the
filled form for human review and never clicks the final button itself.
"""
from __future__ import annotations

import re


class SubmitBlocked(RuntimeError):
    """Raised when an action would submit the application."""


# Final-submission phrasing. Deliberately excludes plain "apply" buttons that
# only open the application form.
SUBMIT_PATTERNS = [
    r"\bsubmit\b",
    r"\bsend (my |your )?application\b",
    r"\bconfirm (and )?(submit|apply)\b",
    r"\bfinalize\b",
    r"\bcomplete (my |your )?application\b",
    r"\bfinish (and )?(submit|apply)\b",
]

_SUBMIT_RE = re.compile("|".join(SUBMIT_PATTERNS), re.IGNORECASE)


def is_submit(element_text: str) -> bool:
    return bool(_SUBMIT_RE.search(element_text or ""))


def assert_not_submit(element_text: str) -> None:
    """Call before every click/type action on a named element."""
    if is_submit(element_text):
        raise SubmitBlocked(
            f"Blocked action on element {element_text!r}: looks like final submission. "
            "Stop here and hand the form to the human for review."
        )
