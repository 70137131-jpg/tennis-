"""Explicit account mode selection; shared local mode is never a production default."""

import os
from urllib.parse import urlsplit


def configured_mode(override=None):
    mode = override or os.environ.get("COURTSIDE_AUTH_MODE") or (
        "academy" if os.environ.get("COURTSIDE_ACCOUNTS") == "1" else "personal"
    )
    if mode not in {"personal", "academy", "local"}:
        raise ValueError("COURTSIDE_AUTH_MODE must be personal, academy, or local")
    if os.environ.get("COURTSIDE_ENV") == "production":
        if mode != "personal":
            raise ValueError("Production requires personal account mode")
        origin = urlsplit(os.environ.get("COURTSIDE_ORIGIN", ""))
        if origin.scheme != "https" or not origin.hostname or origin.path or origin.query or origin.fragment:
            raise ValueError("Production requires COURTSIDE_ORIGIN to be the HTTPS public origin")
    return mode
