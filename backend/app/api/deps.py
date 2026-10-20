import secrets

from fastapi import Header, HTTPException, status

from ..config import get_settings


def require_analyst(x_analyst_token: str | None = Header(default=None)) -> None:
    """Простейшая защита кабинета аналитика: токен в заголовке X-Analyst-Token.
    compare_digest сравнивает строки за постоянное время — так нельзя подобрать токен по задержке ответа.
    Для учебного MVP этого достаточно; в реальном продукте — полноценный вход с JWT и ролями."""
    expected = get_settings().analyst_token
    if not x_analyst_token or not secrets.compare_digest(x_analyst_token.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен аналитика")
