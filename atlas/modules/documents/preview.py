"""Controlled PDF preview rendering with a session-bound watermark."""

from __future__ import annotations

import fitz


class PreviewRenderError(Exception):
    """Input cannot be rendered as a safe controlled PDF preview."""


def render_watermarked_pdf(content: bytes, *, watermark_text: str) -> bytes:
    """Return a metadata-scrubbed PDF with the watermark repeated on every page."""
    if not watermark_text or len(watermark_text) > 500:
        raise PreviewRenderError("watermark text is missing or too long")
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise PreviewRenderError("content is not a readable PDF") from exc
    try:
        if document.page_count == 0:
            raise PreviewRenderError("PDF has no pages")
        document.set_metadata({})
        for page in document:
            page_rect = page.rect
            y = max(36.0, page_rect.height * 0.45)
            page.insert_textbox(
                fitz.Rect(24, y, page_rect.width - 24, y + 80),
                watermark_text,
                fontsize=12,
                fontname="helv",
                color=(0.45, 0.45, 0.45),
                align=fitz.TEXT_ALIGN_CENTER,
                fill_opacity=0.22,
                overlay=True,
            )
        return document.tobytes(garbage=4, deflate=True, clean=True)
    except PreviewRenderError:
        raise
    except Exception as exc:
        raise PreviewRenderError("PDF preview rendering failed") from exc
    finally:
        document.close()
