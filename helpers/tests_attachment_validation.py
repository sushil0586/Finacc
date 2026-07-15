from __future__ import annotations

from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from helpers.utils.attachment_validation import (
    ATTACHMENT_MAX_FILE_SIZE_BYTES,
    validate_attachment_uploads,
)


class AttachmentValidationTests(SimpleTestCase):
    def test_accepts_pdf_excel_text_and_image_files(self):
        files = [
            SimpleUploadedFile("invoice.pdf", b"pdf", content_type="application/pdf"),
            SimpleUploadedFile("report.xls", b"xls", content_type="application/vnd.ms-excel"),
            SimpleUploadedFile(
                "report.xlsx",
                b"xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            SimpleUploadedFile("notes.txt", b"txt", content_type="text/plain"),
            SimpleUploadedFile("scan.webp", b"img", content_type="image/webp"),
        ]

        validate_attachment_uploads(files)

    def test_rejects_unsupported_file_types(self):
        file_obj = SimpleUploadedFile("script.exe", b"exe", content_type="application/octet-stream")

        with self.assertRaises(ValidationError) as exc:
            validate_attachment_uploads([file_obj])

        self.assertEqual(exc.exception.detail["detail"], "script.exe is not a supported format.")

    def test_rejects_oversized_files(self):
        file_obj = SimpleNamespace(
            name="large-scan.pdf",
            size=ATTACHMENT_MAX_FILE_SIZE_BYTES + 1,
            content_type="application/pdf",
        )

        with self.assertRaises(ValidationError) as exc:
            validate_attachment_uploads([file_obj])

        self.assertEqual(exc.exception.detail["detail"], "large-scan.pdf exceeds 15 MB.")

    def test_allows_blank_content_type_when_extension_is_supported(self):
        file_obj = SimpleNamespace(
            name="photo.png",
            size=512,
            content_type="",
        )

        validate_attachment_uploads([file_obj])
