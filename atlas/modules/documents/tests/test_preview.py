"""Controlled PDF preview rendering tests."""

from __future__ import annotations

import fitz
import pytest

from atlas.modules.documents.preview import PreviewRenderError, render_watermarked_pdf

pytestmark = pytest.mark.unit


def synthetic_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Synthetic drawing preview")
    document.set_metadata({"author": "Synthetic Author", "title": "Synthetic Title"})
    content = document.tobytes()
    document.close()
    return content


def test_watermark_is_embedded_on_every_page_and_metadata_is_scrubbed() -> None:
    watermark = "ATLAS user:synthetic session:synthetic utc:2026-08-17T00:00:00Z"
    rendered = render_watermarked_pdf(synthetic_pdf(), watermark_text=watermark)
    document = fitz.open(stream=rendered, filetype="pdf")
    try:
        assert watermark in document[0].get_text()
        assert "Synthetic drawing preview" in document[0].get_text()
        assert not document.metadata.get("author")
        assert not document.metadata.get("title")
    finally:
        document.close()


@pytest.mark.parametrize("content", [b"", b"not a pdf"])
def test_invalid_pdf_is_rejected(content: bytes) -> None:
    with pytest.raises(PreviewRenderError):
        render_watermarked_pdf(content, watermark_text="ATLAS synthetic")


def test_watermark_is_required_and_bounded() -> None:
    with pytest.raises(PreviewRenderError):
        render_watermarked_pdf(synthetic_pdf(), watermark_text="")
    with pytest.raises(PreviewRenderError):
        render_watermarked_pdf(synthetic_pdf(), watermark_text="x" * 501)
