"""PDF template analysis.

For an AcroForm PDF we enumerate the fillable fields. For a flat PDF we
fall back to reporting page geometry so the operator can decide how to
extract field positions later. No data is persisted.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Map AcroForm /FT codes to friendly names.
_FT_NAMES = {
    "/Tx": "text",
    "/Btn": "button",
    "/Ch": "choice",
    "/Sig": "signature",
}


class AnalyzeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class FieldInfo:
    name: str
    type: str
    page: int | None
    rect: list[float] | None
    flags: int
    max_length: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "page": self.page,
            "rect": self.rect,
            "flags": self.flags,
            "max_length": self.max_length,
        }


def _field_type(raw: Any) -> str:
    if raw is None:
        return "unknown"
    key = str(raw)
    return _FT_NAMES.get(key, key.strip("/").lower() or "unknown")


def _locate_field_page(reader: PdfReader, field_obj: Any) -> tuple[int | None, list[float] | None]:
    """Best-effort: find which page the widget annotation lives on."""
    try:
        widget = field_obj.indirect_reference
    except AttributeError:
        widget = None
    if widget is None:
        return None, None
    for idx, page in enumerate(reader.pages):
        annots = page.get("/Annots") or []
        for annot in annots:
            try:
                annot_obj = annot.get_object()
            except AttributeError:
                continue
            if getattr(annot_obj, "indirect_reference", None) == widget:
                rect = annot_obj.get("/Rect")
                rect_list = [float(x) for x in rect] if rect else None
                return idx, rect_list
    return None, None


def _catalog_form_info(reader: PdfReader) -> dict[str, Any]:
    """Inspect the document catalog for form-related entries.

    Distinguishes flat PDFs, XFA forms, and empty/malformed AcroForm
    dictionaries — all three look identical when get_fields() returns
    nothing, so a caller can't otherwise tell why.
    """
    info: dict[str, Any] = {
        "has_acroform_dict": False,
        "has_xfa": False,
        "acroform_field_array_count": 0,
        "need_appearances": False,
    }
    try:
        root = reader.trailer["/Root"]
    except Exception:
        return info

    if "/AcroForm" not in root:
        return info
    try:
        acroform = root["/AcroForm"]
    except Exception:
        return info

    info["has_acroform_dict"] = True

    if "/XFA" in acroform:
        info["has_xfa"] = True

    if "/Fields" in acroform:
        try:
            info["acroform_field_array_count"] = len(acroform["/Fields"])
        except Exception:
            pass

    if "/NeedAppearances" in acroform:
        try:
            info["need_appearances"] = bool(acroform["/NeedAppearances"])
        except Exception:
            pass

    return info


def _classify_form(form_info: dict[str, Any], detected_field_count: int) -> str:
    has_xfa = form_info["has_xfa"]
    has_acro = form_info["has_acroform_dict"]
    if detected_field_count > 0 and has_xfa:
        return "acroform+xfa"
    if detected_field_count > 0:
        return "acroform"
    if has_xfa:
        return "xfa"
    if has_acro:
        return "empty_acroform"
    return "none"


def analyze_pdf_template(data: bytes) -> dict[str, Any]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except PdfReadError as exc:
        raise AnalyzeError("invalid_pdf", "PDF could not be parsed.") from exc

    if reader.is_encrypted:
        raise AnalyzeError("encrypted", "Encrypted PDFs are not supported.")

    pages: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages):
        box = page.mediabox
        pages.append(
            {
                "index": idx,
                "width": float(box.width),
                "height": float(box.height),
            }
        )

    raw_fields = reader.get_fields() or {}
    fields: list[FieldInfo] = []
    for name, obj in raw_fields.items():
        try:
            ft = obj.get("/FT") if hasattr(obj, "get") else None
            flags = int(obj.get("/Ff") or 0) if hasattr(obj, "get") else 0
            max_len_raw = obj.get("/MaxLen") if hasattr(obj, "get") else None
            max_len = int(max_len_raw) if max_len_raw is not None else None
            page_idx, rect = _locate_field_page(reader, obj)
        except Exception:
            ft, flags, max_len, page_idx, rect = None, 0, None, None, None

        fields.append(
            FieldInfo(
                name=str(name),
                type=_field_type(ft),
                page=page_idx,
                rect=rect,
                flags=flags,
                max_length=max_len,
            )
        )

    form_info = _catalog_form_info(reader)
    form_kind = _classify_form(form_info, len(fields))

    return {
        "page_count": len(pages),
        "pages": pages,
        "has_acroform": bool(fields),
        "field_count": len(fields),
        "fields": [f.to_dict() for f in fields],
        "form_kind": form_kind,
        **form_info,
    }
