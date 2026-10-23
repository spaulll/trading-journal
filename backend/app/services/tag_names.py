"""Canonical rules for the words that become tags.

Tag names are stored without their category prefix. The prefix belongs to
the input syntax: ``#fvg`` is a setup, ``!fomo`` is a mistake. A name is
lowercase and may contain letters, digits, underscores, hyphens and slashes;
anything else is a typo or a pasted fragment, not a tag.
"""

from __future__ import annotations

import re
from typing import Optional

MAX_TAG_NAME_LENGTH = 40
_TAG_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_\-/]*$")


def normalize_tag_name(raw: object) -> Optional[str]:
    """Return the canonical tag name, or ``None`` when the token is not one.

    A single leading ``#`` or ``!`` is accepted and removed so a rename field
    can be filled with the same syntax used in the trade ledger. Empty names,
    punctuation-only tokens, dotted numbers and time fragments are rejected.
    """
    if raw is None:
        return None
    name = str(raw).strip().lower()
    if name[:1] in ("#", "!"):
        name = name[1:].strip()
    if not name or len(name) > MAX_TAG_NAME_LENGTH:
        return None
    if not _TAG_NAME_RE.fullmatch(name):
        return None
    return name
