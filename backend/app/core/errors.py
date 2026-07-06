"""共通エラースキーマ（10 §API契約: {"error": {"code", "message", "detail"}}）。"""

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, detail: object | None = None):
        super().__init__(
            status_code=status_code,
            detail={"error": {"code": code, "message": message, "detail": detail}},
        )


def not_found(resource: str = "resource") -> ApiError:
    # 他人のリソースは403でなく404（存在の秘匿。10 §共通事項）
    return ApiError(404, "not_found", f"{resource} not found")


def conflict(message: str, detail: object | None = None) -> ApiError:
    return ApiError(409, "conflict", message, detail)


def validation_error(message: str, detail: object | None = None) -> ApiError:
    return ApiError(422, "validation_error", message, detail)


def payload_too_large(message: str) -> ApiError:
    return ApiError(413, "payload_too_large", message)


def rate_limited(message: str = "Too many requests") -> ApiError:
    return ApiError(429, "rate_limited", message)


def unauthorized(message: str = "Authentication required") -> ApiError:
    return ApiError(401, "unauthorized", message)
