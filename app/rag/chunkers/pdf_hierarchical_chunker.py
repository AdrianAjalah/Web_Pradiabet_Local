"""Hierarchical chunking PDF dengan empat layer.

Layer 0: elemen MinerU yang sudah dibatasi ukuran.
Layer 1: section berdasarkan heading.
Layer 2: konteks per halaman.
Layer 3: ringkasan dokumen.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from app.rag.chunkers.text_splitter import split_text
from app.rag.domain.models import Chunk, DocumentElement


def _id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"chunk-{digest}"


class PdfHierarchicalChunker:
    def __init__(self, max_tokens: int = 900, overlap_tokens: int = 100) -> None:
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(
        self,
        elements: list[DocumentElement],
        source_id: str,
        source_name: str,
        document_summary: str,
    ) -> list[Chunk]:
        if not elements:
            return []

        sections = self._build_sections(elements)
        pages: dict[int, list[DocumentElement]] = defaultdict(list)
        for element in elements:
            pages[element.page].append(element)

        chunks: list[Chunk] = []
        section_chunk_ids: dict[int, str] = {}

        for section_index, section in enumerate(sections):
            title, section_elements = section
            text = "\n".join(element.content for element in section_elements if element.content.strip())
            parts = split_text(text, self.max_tokens, self.overlap_tokens)
            for part_index, part in enumerate(parts):
                chunk_id = _id(source_id, "section", section_index, part_index)
                if part_index == 0:
                    section_chunk_ids[section_index] = chunk_id
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        source_id=source_id,
                        source_name=source_name,
                        source_type="pdf",
                        layer=1,
                        chunk_type="section",
                        content=part,
                        page_start=min(item.page for item in section_elements),
                        page_end=max(item.page for item in section_elements),
                        metadata={"section_title": title, "part_index": part_index},
                    )
                )

        element_to_section = self._map_element_sections(elements)
        for element_index, element in enumerate(elements):
            parent_id = section_chunk_ids.get(element_to_section[element_index])
            for part_index, part in enumerate(split_text(element.content, self.max_tokens, self.overlap_tokens)):
                chunks.append(
                    Chunk(
                        chunk_id=_id(source_id, "element", element.element_id, part_index),
                        source_id=source_id,
                        source_name=source_name,
                        source_type="pdf",
                        layer=0,
                        chunk_type="element",
                        content=part,
                        page_start=element.page,
                        page_end=element.page,
                        parent_chunk_id=parent_id,
                        metadata={
                            "element_id": element.element_id,
                            "element_type": element.element_type,
                            "heading_level": element.heading_level,
                            "image_path": element.image_path,
                            "part_index": part_index,
                        },
                    )
                )

        for page, page_elements in sorted(pages.items()):
            page_text = "\n".join(item.content for item in page_elements if item.content.strip())
            for part_index, part in enumerate(split_text(page_text, self.max_tokens, self.overlap_tokens)):
                chunks.append(
                    Chunk(
                        chunk_id=_id(source_id, "page", page, part_index),
                        source_id=source_id,
                        source_name=source_name,
                        source_type="pdf",
                        layer=2,
                        chunk_type="page",
                        content=part,
                        page_start=page,
                        page_end=page,
                        metadata={"page": page, "part_index": part_index},
                    )
                )

        if document_summary.strip():
            chunks.append(
                Chunk(
                    chunk_id=_id(source_id, "summary"),
                    source_id=source_id,
                    source_name=source_name,
                    source_type="pdf",
                    layer=3,
                    chunk_type="document_summary",
                    content=document_summary.strip(),
                    page_start=min(pages),
                    page_end=max(pages),
                )
            )
        return chunks

    @staticmethod
    def _build_sections(elements: list[DocumentElement]) -> list[tuple[str, list[DocumentElement]]]:
        sections: list[tuple[str, list[DocumentElement]]] = []
        title = "Pembuka Dokumen"
        current: list[DocumentElement] = []
        for element in elements:
            if element.element_type == "title" and current:
                sections.append((title, current))
                title = element.content
                current = [element]
            else:
                if element.element_type == "title":
                    title = element.content
                current.append(element)
        if current:
            sections.append((title, current))
        return sections

    @staticmethod
    def _map_element_sections(elements: list[DocumentElement]) -> dict[int, int]:
        result: dict[int, int] = {}
        section_index = 0
        has_content = False
        for index, element in enumerate(elements):
            if element.element_type == "title" and has_content:
                section_index += 1
            result[index] = section_index
            has_content = True
        return result
