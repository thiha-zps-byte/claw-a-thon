"""Unified error model.

Every error surfaced to the client uses the same envelope so the frontend can
render a friendly Vietnamese message and decide whether to offer a retry. We
never leak stack traces or secrets to the client.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    """An error meant to be shown to the user.

    Attributes:
        code: machine-readable error code (snake_case).
        message: friendly Vietnamese message safe to show the player.
        status: HTTP status code.
        detail: optional non-sensitive debug detail.
        retryable: whether the client should offer a "try again" action.
    """

    code: str
    message: str
    status: int = 400
    detail: str = ""
    retryable: bool = False

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_envelope(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "detail": self.detail,
            "retryable": self.retryable,
        }


# --- Common factory helpers (consistent Vietnamese user messages) ---


def validation_error(message: str, detail: str = "") -> AppError:
    return AppError("validation_error", message, status=400, detail=detail)


def not_found(message: str = "Không tìm thấy.", detail: str = "") -> AppError:
    return AppError("not_found", message, status=404, detail=detail)


def upload_too_large(max_mb: int) -> AppError:
    return AppError(
        "upload_too_large",
        f"File quá lớn. Vui lòng tải file dưới {max_mb}MB.",
        status=413,
    )


def unsupported_format(detail: str = "") -> AppError:
    return AppError(
        "unsupported_format",
        "Định dạng file không được hỗ trợ. Hãy dùng .md, .txt, .pdf, .docx, .csv hoặc ảnh.",
        status=400,
        detail=detail,
    )


def llm_unavailable(detail: str = "") -> AppError:
    return AppError(
        "llm_unavailable",
        "Hệ thống đang bận, bạn vui lòng thử lại sau ít phút nhé.",
        status=503,
        detail=detail,
        retryable=True,
    )


def internal_error(detail: str = "") -> AppError:
    return AppError(
        "internal_error",
        "Có lỗi xảy ra phía hệ thống. Bạn thử lại giúp mình nhé.",
        status=500,
        detail=detail,
        retryable=True,
    )
