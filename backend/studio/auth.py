"""Local app sessions and the explicit credential used by agent connections."""

import hmac
import os
import secrets

COOKIE = "composer_session"


def matches(candidate: str, expected: str) -> bool:
    return bool(candidate and expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def bearer(headers) -> str:
    value = headers.get("authorization", "")
    return value[7:] if value.lower().startswith("bearer ") else ""


def app_allowed(connection) -> bool:
    expected = os.environ.get("MANIM_API_TOKEN", "")
    return not expected or matches(bearer(connection.headers), expected) or matches(connection.cookies.get(COOKIE, ""), expected)


def agent_token(workspace: str) -> str:
    """Keep one credential per workspace so saved MCP client configurations keep working."""
    explicit = os.environ.get("MANIM_MCP_TOKEN")
    if explicit:
        return explicit
    folder = os.path.join(workspace, "studio")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "mcp-token")
    try:
        with open(path, encoding="ascii") as f:
            value = f.read().strip()
        if len(value) >= 32:
            return value
        raise RuntimeError("The Studio agent token file is invalid; remove it to create a new credential.")
    except FileNotFoundError:
        value = secrets.token_urlsafe(32)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return agent_token(workspace)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(value)
        return value
