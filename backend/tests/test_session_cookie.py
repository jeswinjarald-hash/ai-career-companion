import pytest
from fastapi import Response

from app.core.config import get_settings
from app.services import auth


class _Settings:
    def __init__(self, app_env: str, session_cookie_secure: bool | None) -> None:
        self.app_env = app_env
        self.session_cookie_secure = session_cookie_secure


@pytest.mark.parametrize(
    ("app_env", "override", "expected"),
    [
        ("development", None, False),  # plain http://localhost must keep working
        ("production", None, True),
        ("staging", None, True),
        ("production", False, False),  # explicit override wins
        ("development", True, True),
    ],
)
def test_session_cookie_secure_flag(monkeypatch: pytest.MonkeyPatch, app_env: str, override: bool | None, expected: bool) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _Settings(app_env, override))
    assert auth.session_cookie_secure() is expected

    response = Response()
    response.set_cookie(auth.SESSION_COOKIE, "token", httponly=True, samesite="lax", secure=auth.session_cookie_secure())
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert ("secure" in header.replace("samesite", "")) is expected


def test_default_settings_keep_local_development_cookie_insecure() -> None:
    settings = get_settings()
    if settings.app_env == "development" and settings.session_cookie_secure is None:
        assert auth.session_cookie_secure() is False
