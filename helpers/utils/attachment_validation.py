from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable

from rest_framework.exceptions import ValidationError

ATTACHMENT_MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024
ATTACHMENT_MAX_FILE_SIZE_MB = 15

_EXACT_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".xls",
    ".xlsx",
    ".apng",
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".ico",
    ".jfif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}


def validate_attachment_uploads(
    files: Iterable[object],
    *,
    max_size_bytes: int = ATTACHMENT_MAX_FILE_SIZE_BYTES,
) -> None:
    for file_obj in files:
        if not file_obj:
            continue

        file_name = str(getattr(file_obj, "name", "") or "").strip() or "File"
        file_size = int(getattr(file_obj, "size", 0) or 0)
        if file_size > max_size_bytes:
            raise ValidationError({"detail": f"{file_name} exceeds {ATTACHMENT_MAX_FILE_SIZE_MB} MB."})

        if not _is_supported_attachment_type(file_obj):
            raise ValidationError({"detail": f"{file_name} is not a supported format."})


def _is_supported_attachment_type(file_obj: object) -> bool:
    declared_type = str(getattr(file_obj, "content_type", "") or "").strip().lower()
    guessed_type, _ = mimetypes.guess_type(str(getattr(file_obj, "name", "") or ""))
    guessed_type = str(guessed_type or "").strip().lower()

    for mime_type in (declared_type, guessed_type):
        if not mime_type:
            continue
        if mime_type.startswith("image/"):
            return True
        if mime_type in _EXACT_ALLOWED_MIME_TYPES:
            return True

    suffix = Path(str(getattr(file_obj, "name", "") or "")).suffix.lower()
    return suffix in _ALLOWED_EXTENSIONS
