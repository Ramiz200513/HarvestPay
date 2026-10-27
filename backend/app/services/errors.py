"""Понятные сообщения об ошибках внешних сервисов — вместо «HTTPStatusError: 401 Unauthorized ...»."""

from __future__ import annotations

import httpx


def describe_external_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "Сервис спутниковых снимков отклонил ключ доступа — администратору нужно проверить ключи"
        if code == 429:
            return "Сервис спутниковых снимков временно ограничил число запросов — попробуйте через минуту"
        if code >= 500:
            return "Сервис спутниковых снимков временно не работает — попробуйте позже"
        return f"Сервис спутниковых снимков вернул ошибку {code}"
    if isinstance(exc, httpx.TimeoutException):
        return "Сервис спутниковых снимков не ответил вовремя — попробуйте позже"
    if isinstance(exc, httpx.TransportError):
        return "Нет связи с сервисом спутниковых снимков — проверьте подключение к интернету"
    if isinstance(exc, RuntimeError):
        return str(exc)  # ошибки настройки (нет ключа и т.п.) мы пишем сами, по-русски
    return "Не удалось получить спутниковые данные или рассчитать скоринг"
