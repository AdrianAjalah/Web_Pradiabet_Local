from app.rag.domain.models import Chunk, DocumentElement


def test_chunk_payload_preserves_parent_and_source_metadata():
    element = DocumentElement(element_id="e1", element_type="text", content="Isi", page=2)
    chunk = Chunk(
        chunk_id="c1",
        source_id="doc-1",
        source_name="panduan.pdf",
        source_type="pdf",
        layer=0,
        chunk_type="element",
        content=element.content,
        page_start=2,
        page_end=2,
        parent_chunk_id="section-1",
        metadata={"element_type": element.element_type},
    )

    payload = chunk.to_payload()
    assert payload["parent_chunk_id"] == "section-1"
    assert payload["source_type"] == "pdf"
    assert payload["page_start"] == 2
