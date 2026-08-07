from __future__ import annotations


class RefactorAppError(Exception):
    error_code = "internal_error"


class NotFoundError(RefactorAppError):
    error_code = "not_found"


class ValidationError(RefactorAppError):
    error_code = "validation_error"
