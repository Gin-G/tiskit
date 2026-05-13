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

    return {
        "page_count": len(pages),
        "pages": pages,
        "has_acroform": bool(fields),
        "field_count": len(fields),
        "fields": [f.to_dict() for f in fields],
    }
