from app.rag.chunkers.pdf_hierarchical_chunker import PdfHierarchicalChunker
from app.rag.domain.models import DocumentElement


def test_pdf_chunker_builds_four_layers_and_parent_links():
    elements = [
        DocumentElement("e1", "title", "Pendahuluan", 1, heading_level=1),
        DocumentElement("e2", "text", "Prediabetes adalah kondisi awal. " * 20, 1),
        DocumentElement("e3", "title", "Pola makan", 2, heading_level=1),
        DocumentElement("e4", "text", "Pola makan seimbang membantu. " * 20, 2),
    ]
    chunker = PdfHierarchicalChunker(max_tokens=45, overlap_tokens=5)

    chunks = chunker.chunk(elements, source_id="doc-1", source_name="panduan.pdf", document_summary="Ringkasan")

    assert {chunk.layer for chunk in chunks} == {0, 1, 2, 3}
    element_chunks = [chunk for chunk in chunks if chunk.layer == 0]
    assert element_chunks
    assert all(chunk.parent_chunk_id for chunk in element_chunks)
    assert all(len(chunk.content.split()) <= 45 for chunk in chunks if chunk.layer != 3)
    assert [chunk for chunk in chunks if chunk.layer == 3][0].content == "Ringkasan"
