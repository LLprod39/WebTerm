from __future__ import annotations


class ActionRequestValidationError(ValueError):
    def __init__(self, message: str, *, code: str, payload: dict | None = None):
        super().__init__(message)
        self.code = code
        self.payload = payload or {}
