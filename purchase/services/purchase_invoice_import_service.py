from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from catalog.models import Product
from financial.models import account
from financial.profile_access import account_gstno
from helpers.utils.openai_client import generate_multimodal_text, generate_text


GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b", re.IGNORECASE)
DATE_PATTERNS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y")


@dataclass
class PurchaseInvoiceImportContext:
    entity_id: int
    entityfinid: int
    subentity_id: int | None
    line_mode: str


class PurchaseInvoiceImportService:
    @classmethod
    def build_import_draft(cls, *, uploaded_file: Any, context: PurchaseInvoiceImportContext) -> dict[str, Any]:
        file_name = str(getattr(uploaded_file, "name", "") or "uploaded-file").strip() or "uploaded-file"
        file_bytes = uploaded_file.read()
        file_kind = cls._resolve_file_kind(file_name)
        warnings: list[dict[str, Any]] = []

        extracted_text = cls._extract_text(file_name=file_name, file_kind=file_kind, file_bytes=file_bytes, warnings=warnings)
        parsed_header = cls._parse_header(extracted_text)
        parsed_lines = cls._parse_lines(extracted_text)
        media_ai_structured = cls._parse_media_with_ai(file_kind, file_name, file_bytes, warnings=warnings)
        ai_structured = cls._parse_with_ai(extracted_text, warnings=warnings) if cls._should_attempt_ai_structuring(parsed_header, parsed_lines, file_kind) else None
        if media_ai_structured:
            parsed_header = cls._merge_header(parsed_header, media_ai_structured.get("header") or {})
            parsed_lines = cls._merge_lines(parsed_lines, media_ai_structured.get("lines") or [])
        if ai_structured:
            parsed_header = cls._merge_header(parsed_header, ai_structured.get("header") or {})
            parsed_lines = cls._merge_lines(parsed_lines, ai_structured.get("lines") or [])
        vendor_match = cls._match_vendor(context.entity_id, parsed_header.get("vendor_name"), parsed_header.get("vendor_gstin"))
        product_lines = cls._match_products(context.entity_id, parsed_lines)

        if file_kind == "image" and not media_ai_structured:
            warnings.append({
                "code": "image_ocr_pending",
                "message": "Image OCR/vision extraction is unavailable right now, so only the uploaded file is staged for review.",
                "field": None,
                "line_index": None,
            })
        if file_kind == "pdf" and not extracted_text.strip() and not media_ai_structured:
            warnings.append({
                "code": "pdf_ocr_pending",
                "message": "This PDF does not contain machine-readable text, and image-based PDF OCR is not enabled yet.",
                "field": None,
                "line_index": None,
            })
        if not extracted_text.strip() and not media_ai_structured:
            warnings.append({
                "code": "no_text_extracted",
                "message": "No machine-readable text could be extracted from the uploaded document.",
                "field": None,
                "line_index": None,
            })
        if vendor_match["status"] != "matched":
            warnings.append({
                "code": "vendor_unresolved",
                "message": "Vendor could not be matched confidently. Please review or create the vendor before final save.",
                "field": "vendor",
                "line_index": None,
            })
        if any(item["product_match"]["status"] != "matched" for item in product_lines):
            warnings.append({
                "code": "product_unresolved",
                "message": "One or more imported lines are not mapped to an existing product yet.",
                "field": "lines",
                "line_index": None,
            })

        matched_product_count = sum(1 for item in product_lines if item["product_match"]["status"] == "matched")
        confidence = 0.25
        if extracted_text.strip():
            confidence += 0.25
        if vendor_match["status"] == "matched":
            confidence += 0.25
        if product_lines:
            confidence += 0.25 * (matched_product_count / max(len(product_lines), 1))

        return {
            "source_file": {
                "name": file_name,
                "kind": file_kind,
            },
            "header": parsed_header,
            "lines": product_lines,
            "warnings": warnings,
            "extracted_text_preview": extracted_text[:2000],
            "matches": {
                "vendor": vendor_match,
            },
            "confidence": {
                "overall": round(min(max(confidence, 0), 1), 2),
            },
        }

    @classmethod
    def _resolve_file_kind(cls, file_name: str) -> str:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix == ".txt":
            return "txt"
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif"}:
            return "image"
        return "unknown"

    @classmethod
    def _extract_text(cls, *, file_name: str, file_kind: str, file_bytes: bytes, warnings: list[dict[str, Any]]) -> str:
        if file_kind == "txt":
            return cls._decode_text(file_bytes)
        if file_kind == "pdf":
            try:
                reader = PdfReader(BytesIO(file_bytes))
                return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
            except Exception:
                warnings.append({
                    "code": "pdf_extract_failed",
                    "message": f"Unable to read text from {file_name}.",
                    "field": None,
                    "line_index": None,
                })
                return ""
        return ""

    @classmethod
    def _decode_text(cls, file_bytes: bytes) -> str:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return file_bytes.decode(encoding).strip()
            except Exception:
                continue
        return ""

    @classmethod
    def _parse_header(cls, extracted_text: str) -> dict[str, Any]:
        lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
        vendor_name = cls._extract_labeled_value(lines, ("vendor", "supplier", "party"))
        supplier_invoice_number = cls._extract_labeled_value(lines, ("invoice no", "invoice number", "bill no", "bill number"))
        supplier_invoice_date = cls._normalize_date(cls._extract_labeled_value(lines, ("invoice date", "bill date", "date")))
        grand_total = cls._extract_amount(lines, ("grand total", "invoice total", "net amount", "total amount"))
        gstin_match = GSTIN_RE.search(extracted_text or "")
        vendor_gstin = gstin_match.group(0).upper() if gstin_match else None

        if not vendor_name and lines:
            vendor_name = lines[0][:200]

        return {
            "supplier_invoice_number": supplier_invoice_number,
            "supplier_invoice_date": supplier_invoice_date,
            "bill_date": supplier_invoice_date,
            "due_date": supplier_invoice_date,
            "vendor_name": vendor_name,
            "vendor_gstin": vendor_gstin,
            "vendor_state_code": vendor_gstin[:2] if vendor_gstin else None,
            "place_of_supply_state_code": vendor_gstin[:2] if vendor_gstin else None,
            "tax_regime": 1 if vendor_gstin else None,
            "supply_category": None,
            "taxability": None,
            "grand_total": grand_total,
        }

    @classmethod
    def _parse_lines(cls, extracted_text: str) -> list[dict[str, Any]]:
        parsed_lines: list[dict[str, Any]] = []
        candidate_lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
        for raw_line in candidate_lines:
            parsed = cls._parse_candidate_line(raw_line, len(parsed_lines) + 1)
            if parsed:
                parsed_lines.append(parsed)
        return parsed_lines[:25]

    @classmethod
    def _parse_candidate_line(cls, raw_line: str, line_no: int) -> dict[str, Any] | None:
        if len(raw_line) < 4:
            return None
        separator_based = cls._parse_separator_line(raw_line, line_no)
        if separator_based:
            return separator_based
        amount_matches = re.findall(r"(?<!\d)(\d+(?:\.\d{1,2})?)(?!\d)", raw_line)
        if len(amount_matches) < 2:
            return None
        qty = cls._to_number(amount_matches[-3]) if len(amount_matches) >= 3 else 1
        rate = cls._to_number(amount_matches[-2]) if len(amount_matches) >= 2 else None
        amount = cls._to_number(amount_matches[-1]) if amount_matches else None
        description = re.sub(r"\s+", " ", re.sub(r"(?<!\d)\d+(?:\.\d{1,2})?(?!\d)", " ", raw_line)).strip(" -|:")
        if not description:
            return None
        gst_rate = None
        gst_rate_match = re.search(r"\b(5|12|18|28|0)(?:\s*%)\b", raw_line)
        if gst_rate_match:
            gst_rate = cls._to_number(gst_rate_match.group(1))
        hsn_match = re.search(r"\bHSN[:\s-]*([A-Z0-9]{4,10})\b", raw_line, flags=re.IGNORECASE)

        return {
            "line_no": line_no,
            "description": description[:500],
            "product_name": description[:200],
            "qty": qty,
            "rate": rate,
            "amount": amount,
            "hsn": hsn_match.group(1) if hsn_match else None,
            "gst_rate": gst_rate,
            "taxability": None,
        }

    @classmethod
    def _parse_separator_line(cls, raw_line: str, line_no: int) -> dict[str, Any] | None:
        if "|" in raw_line:
            parts = [part.strip() for part in raw_line.split("|") if part.strip()]
        elif "\t" in raw_line:
            parts = [part.strip() for part in raw_line.split("\t") if part.strip()]
        else:
            return None

        if len(parts) < 3:
            return None

        description = parts[0]
        qty = cls._to_number(parts[-3]) if len(parts) >= 3 else None
        rate = cls._to_number(parts[-2]) if len(parts) >= 2 else None
        amount = cls._to_number(parts[-1]) if len(parts) >= 1 else None
        if qty is None and rate is None and amount is None:
            return None
        return {
            "line_no": line_no,
            "description": description[:500],
            "product_name": description[:200],
            "qty": qty,
            "rate": rate,
            "amount": amount,
            "hsn": None,
            "gst_rate": None,
            "taxability": None,
        }

    @classmethod
    def _extract_labeled_value(cls, lines: Iterable[str], labels: tuple[str, ...]) -> str | None:
        normalized_labels = tuple(label.lower() for label in labels)
        for line in lines:
            lower_line = line.lower()
            for label in normalized_labels:
                if label in lower_line:
                    tail = re.split(r"[:\-]", line, maxsplit=1)
                    value = tail[1].strip() if len(tail) > 1 else line.strip()
                    if value:
                        return value[:200]
        return None

    @classmethod
    def _extract_amount(cls, lines: Iterable[str], labels: tuple[str, ...]) -> float | None:
        value = cls._extract_labeled_value(lines, labels)
        if not value:
            return None
        match = re.search(r"(-?\d[\d,]*\.?\d{0,2})", value.replace(",", ""))
        return cls._to_number(match.group(1)) if match else None

    @classmethod
    def _normalize_date(cls, raw_value: str | None) -> str | None:
        if not raw_value:
            return None
        token_match = re.search(r"\b\d{1,4}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b", raw_value)
        if not token_match:
            return None
        token = token_match.group(0).replace(".", "-").replace("/", "-")
        for pattern in DATE_PATTERNS:
            try:
                return datetime.strptime(token, pattern.replace("/", "-").replace(".", "-")).date().isoformat()
            except Exception:
                continue
        return None

    @classmethod
    def _match_vendor(cls, entity_id: int, vendor_name: str | None, vendor_gstin: str | None) -> dict[str, Any]:
        candidates = []
        matched = None

        if vendor_gstin:
            matched = account.objects.filter(entity_id=entity_id, compliance_profile__gstno__iexact=vendor_gstin).first()
        if not matched and vendor_name:
            exact_matches = list(account.objects.filter(entity_id=entity_id, accountname__iexact=vendor_name).order_by("accountname", "id")[:5])
            if len(exact_matches) == 1:
                matched = exact_matches[0]
            elif len(exact_matches) > 1:
                candidates = exact_matches
        if not matched and not candidates and vendor_name:
            candidates = list(account.objects.filter(entity_id=entity_id, accountname__icontains=vendor_name).order_by("accountname", "id")[:5])

        if matched:
            return {
                "status": "matched",
                "id": matched.id,
                "name": matched.accountname,
                "gstin": account_gstno(matched),
                "candidates": [],
            }
        return {
            "status": "multiple" if len(candidates) > 1 else "unresolved",
            "id": None,
            "name": vendor_name,
            "gstin": vendor_gstin,
            "candidates": [
                {"id": item.id, "name": item.accountname, "gstin": account_gstno(item)}
                for item in candidates
            ],
        }

    @classmethod
    def _match_products(cls, entity_id: int, parsed_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for line in parsed_lines:
            product_name = str(line.get("product_name") or line.get("description") or "").strip()
            matched = None
            candidates = []
            if product_name:
                exact_matches = list(Product.objects.filter(entity_id=entity_id, productname__iexact=product_name).order_by("productname", "id")[:5])
                if len(exact_matches) == 1:
                    matched = exact_matches[0]
                elif len(exact_matches) > 1:
                    candidates = exact_matches
                else:
                    candidates = list(Product.objects.filter(entity_id=entity_id, productname__icontains=product_name).order_by("productname", "id")[:5])

            enriched = dict(line)
            if matched:
                enriched["product_match"] = {
                    "status": "matched",
                    "id": matched.id,
                    "name": matched.productname,
                    "candidates": [],
                }
                enriched["product_name"] = matched.productname
                enriched["hsn"] = line.get("hsn") or getattr(matched, "hsn", None)
            else:
                enriched["product_match"] = {
                    "status": "multiple" if len(candidates) > 1 else "unresolved",
                    "id": None,
                    "name": product_name or None,
                    "candidates": [
                        {
                            "id": item.id,
                            "name": item.productname,
                            "hsn": getattr(item, "hsn", None),
                        }
                        for item in candidates
                    ],
                }
            results.append(enriched)
        return results

    @classmethod
    def _should_attempt_ai_structuring(
        cls,
        parsed_header: dict[str, Any],
        parsed_lines: list[dict[str, Any]],
        file_kind: str,
    ) -> bool:
        if file_kind == "image":
            return False
        if parsed_header.get("vendor_name") and len(parsed_lines) >= 2:
            return False
        return True

    @classmethod
    def _parse_media_with_ai(
        cls,
        file_kind: str,
        file_name: str,
        file_bytes: bytes,
        *,
        warnings: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        media_payload: tuple[bytes, str, str] | None = None
        if file_kind == "image":
            media_payload = (
                file_bytes,
                mimetypes.guess_type(file_name)[0] or "image/png",
                "invoice image",
            )
        elif file_kind == "pdf":
            media_payload = cls._extract_pdf_embedded_image(file_name, file_bytes, warnings=warnings)
            if media_payload is None:
                media_payload = cls._render_pdf_first_page_image(file_name, file_bytes, warnings=warnings)

        if media_payload is None:
            return None
        prompt = (
            "Extract purchase invoice data from this invoice document and respond with JSON only. "
            "Use this shape: "
            '{"header":{"vendor_name":null,"vendor_gstin":null,"supplier_invoice_number":null,"supplier_invoice_date":null,"bill_date":null,"due_date":null,"grand_total":null},'
            '"lines":[{"description":"","product_name":null,"qty":null,"rate":null,"amount":null,"hsn":null,"gst_rate":null,"taxability":null}]}. '
            "If a value is unknown use null. Do not include markdown fences."
        )
        media_bytes, media_mime_type, _source_label = media_payload
        try:
            raw = generate_multimodal_text(
                prompt,
                media_bytes=media_bytes,
                media_mime_type=media_mime_type,
            )
            parsed = cls._extract_json_object(raw)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except Exception:
            warnings.append({
                "code": "image_ai_unavailable" if file_kind == "image" else "pdf_ai_unavailable",
                "message": "Vision-based extraction is unavailable, so the document could not be parsed automatically.",
                "field": None,
                "line_index": None,
            })
            return None

    @classmethod
    def _extract_pdf_embedded_image(
        cls,
        file_name: str,
        file_bytes: bytes,
        *,
        warnings: list[dict[str, Any]],
    ) -> tuple[bytes, str, str] | None:
        try:
            reader = PdfReader(BytesIO(file_bytes))
        except Exception:
            return None

        for page_index, page in enumerate(reader.pages, start=1):
            images = getattr(page, "images", None)
            if not images:
                continue
            try:
                iterable = list(images)
            except Exception:
                continue
            for image_index, image in enumerate(iterable, start=1):
                data = getattr(image, "data", None)
                name = str(getattr(image, "name", "") or f"{Path(file_name).stem}-page{page_index}-image{image_index}.png")
                if data is None:
                    image_file = getattr(image, "image", None)
                    if image_file is not None and hasattr(image_file, "tobytes"):
                        try:
                            data = image_file.tobytes()
                        except Exception:
                            data = None
                if data is None:
                    continue
                mime_type = mimetypes.guess_type(name)[0] or "image/png"
                return (bytes(data), mime_type, f"page {page_index} image {image_index}")

        warnings.append({
            "code": "pdf_embedded_images_missing",
            "message": "This PDF did not expose embedded page images for vision-based extraction.",
            "field": None,
            "line_index": None,
        })
        return None

    @classmethod
    def _render_pdf_first_page_image(
        cls,
        file_name: str,
        file_bytes: bytes,
        *,
        warnings: list[dict[str, Any]],
    ) -> tuple[bytes, str, str] | None:
        renderers = (
            cls._render_pdf_first_page_with_pdftoppm,
            cls._render_pdf_first_page_with_ghostscript,
        )
        for renderer in renderers:
            try:
                rendered = renderer(file_name, file_bytes)
            except Exception:
                rendered = None
            if rendered is not None:
                return rendered
        warnings.append({
            "code": "pdf_rasterizer_unavailable",
            "message": "No PDF rasterization tool is available for scanned PDF OCR fallback.",
            "field": None,
            "line_index": None,
        })
        return None

    @classmethod
    def _render_pdf_first_page_with_pdftoppm(
        cls,
        file_name: str,
        file_bytes: bytes,
    ) -> tuple[bytes, str, str] | None:
        executable = shutil.which("pdftoppm")
        if not executable:
            return None
        with tempfile.TemporaryDirectory(prefix="purchase-import-pdf-") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / file_name
            output_base = temp_path / "page-1"
            input_path.write_bytes(file_bytes)
            result = subprocess.run(
                [
                    executable,
                    "-f",
                    "1",
                    "-singlefile",
                    "-png",
                    str(input_path),
                    str(output_base),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            if result.returncode != 0:
                return None
            output_path = output_base.with_suffix(".png")
            if not output_path.exists():
                return None
            return (output_path.read_bytes(), "image/png", "page 1 rasterized by pdftoppm")

    @classmethod
    def _render_pdf_first_page_with_ghostscript(
        cls,
        file_name: str,
        file_bytes: bytes,
    ) -> tuple[bytes, str, str] | None:
        executable = shutil.which("gs")
        if not executable:
            return None
        with tempfile.TemporaryDirectory(prefix="purchase-import-pdf-gs-") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / file_name
            output_path = temp_path / "page-1.png"
            input_path.write_bytes(file_bytes)
            result = subprocess.run(
                [
                    executable,
                    "-dSAFER",
                    "-dBATCH",
                    "-dNOPAUSE",
                    "-sDEVICE=png16m",
                    "-dFirstPage=1",
                    "-dLastPage=1",
                    f"-sOutputFile={output_path}",
                    str(input_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            if result.returncode != 0 or not output_path.exists():
                return None
            return (output_path.read_bytes(), "image/png", "page 1 rasterized by ghostscript")

    @classmethod
    def _parse_with_ai(cls, extracted_text: str, *, warnings: list[dict[str, Any]]) -> dict[str, Any] | None:
        text = str(extracted_text or "").strip()
        if not text:
            return None

        prompt = (
            "Extract purchase invoice data from the text below and respond with JSON only. "
            "Use this shape: "
            '{"header":{"vendor_name":null,"vendor_gstin":null,"supplier_invoice_number":null,"supplier_invoice_date":null,"bill_date":null,"due_date":null,"grand_total":null},'
            '"lines":[{"description":"","product_name":null,"qty":null,"rate":null,"amount":null,"hsn":null,"gst_rate":null,"taxability":null}]}. '
            "If a value is unknown use null. Do not include markdown fences.\n\n"
            f"Invoice text:\n{text[:12000]}"
        )
        try:
            raw = generate_text(prompt)
            parsed = cls._extract_json_object(raw)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except Exception:
            warnings.append({
                "code": "ai_structuring_unavailable",
                "message": "AI-assisted structuring is unavailable, so draft extraction used deterministic parsing only.",
                "field": None,
                "line_index": None,
            })
            return None

    @classmethod
    def _extract_json_object(cls, raw_text: str) -> dict[str, Any] | None:
        text = str(raw_text or "").strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    @classmethod
    def _merge_header(cls, base_header: dict[str, Any], ai_header: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base_header)
        for key in (
            "vendor_name",
            "vendor_gstin",
            "supplier_invoice_number",
            "supplier_invoice_date",
            "bill_date",
            "due_date",
            "grand_total",
            "vendor_state_code",
            "place_of_supply_state_code",
            "tax_regime",
            "supply_category",
            "taxability",
        ):
            current_value = merged.get(key)
            if current_value not in (None, "", []):
                continue
            next_value = ai_header.get(key)
            if next_value in (None, "", []):
                continue
            if key.endswith("_date"):
                merged[key] = cls._normalize_date(str(next_value))
            elif key == "grand_total":
                merged[key] = cls._to_number(next_value)
            else:
                merged[key] = next_value
        gstin = str(merged.get("vendor_gstin") or "").strip().upper()
        if gstin:
            merged["vendor_gstin"] = gstin
            merged["vendor_state_code"] = merged.get("vendor_state_code") or gstin[:2]
            merged["place_of_supply_state_code"] = merged.get("place_of_supply_state_code") or gstin[:2]
            merged["tax_regime"] = merged.get("tax_regime") or 1
        return merged

    @classmethod
    def _merge_lines(cls, base_lines: list[dict[str, Any]], ai_lines: list[Any]) -> list[dict[str, Any]]:
        normalized_ai_lines = [cls._normalize_ai_line(item, index + 1) for index, item in enumerate(ai_lines or [])]
        normalized_ai_lines = [item for item in normalized_ai_lines if item]
        if not normalized_ai_lines:
            return base_lines
        if not base_lines:
            return normalized_ai_lines

        merged: list[dict[str, Any]] = []
        for index, line in enumerate(base_lines, start=1):
            merged_line = dict(line)
            ai_line = normalized_ai_lines[index - 1] if index - 1 < len(normalized_ai_lines) else None
            if ai_line:
                for key in ("description", "product_name", "qty", "rate", "amount", "hsn", "gst_rate", "taxability"):
                    if merged_line.get(key) in (None, "", []):
                        merged_line[key] = ai_line.get(key)
            merged_line["line_no"] = index
            merged.append(merged_line)
        return merged

    @classmethod
    def _normalize_ai_line(cls, raw_line: Any, line_no: int) -> dict[str, Any] | None:
        if not isinstance(raw_line, dict):
            return None
        description = str(raw_line.get("description") or raw_line.get("product_name") or "").strip()
        if not description:
            return None
        return {
            "line_no": line_no,
            "description": description[:500],
            "product_name": str(raw_line.get("product_name") or description).strip()[:200] or None,
            "qty": cls._to_number(raw_line.get("qty")),
            "rate": cls._to_number(raw_line.get("rate")),
            "amount": cls._to_number(raw_line.get("amount")),
            "hsn": str(raw_line.get("hsn") or "").strip() or None,
            "gst_rate": cls._to_number(raw_line.get("gst_rate")),
            "taxability": cls._to_number(raw_line.get("taxability")),
        }

    @classmethod
    def _to_number(cls, raw_value: Any) -> float | None:
        try:
            return round(float(str(raw_value).replace(",", "").strip()), 2)
        except Exception:
            return None
