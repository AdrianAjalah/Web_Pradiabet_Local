"""Penulisan dan pembacaan artefak hasil pipeline RAG.

Semua file ditulis atomik agar dashboard tidak pernah membaca file setengah jadi.
Artefak menyimpan seluruh hasil; batas 50 hanya diterapkan pada respons web.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.rag.domain.models import Chunk, DocumentElement, QaPair



FOOD_FLAG_LABELS = {
    "mengandung_susu": "Mengandung Susu",
    "mengandung_telur": "Mengandung Telur",
    "mengandung_seafood": "Mengandung Seafood",
    "mengandung_kacang": "Mengandung Kacang",
    "mengandung_babi": "Mengandung Babi",
    "mengandung_santan": "Mengandung Santan",
    "mengandung_alkohol": "Mengandung Alkohol",
    "mengandung_sayur": "Mengandung Sayur",
    "adalah_gorengan": "Adalah Gorengan",
    "sumber_karbohidrat": "Sumber Karbohidrat",
    "karbohidrat_kompleks": "Karbohidrat Kompleks",
    "karbohidrat_olahan": "Karbohidrat Olahan",
}


def _food_flag_markdown(payload: dict) -> list[str]:
    if not any(key in payload for key in FOOD_FLAG_LABELS):
        return []
    rows = ["- **Flag makanan:**", ""]
    for key, label in FOOD_FLAG_LABELS.items():
        rows.append(f"  - {label}: {'Ya' if bool(payload.get(key)) else 'Tidak'}")
    rows.append("")
    return rows

ARTIFACT_FILENAMES = (
    "extracted.md",
    "chunks.md",
    "chunks.json",
    "qa.md",
    "qa.json",
    "reindex_summary.json",
)


class RagArtifactWriter:
    def write_pdf_extraction(
        self,
        output_dir: Path,
        source_name: str,
        elements: Iterable[DocumentElement],
    ) -> Path:
        markdown = self._elements_to_markdown(elements)
        return self._write_text(Path(output_dir) / "extracted.md", markdown)

    def write_chunks(self, output_dir: Path, chunks: Iterable[Chunk]) -> tuple[Path, Path]:
        chunk_list = list(chunks)
        json_rows = [chunk.to_payload() for chunk in chunk_list]
        markdown_parts: list[str] = ["# Hasil Chunking", ""]
        for index, chunk in enumerate(chunk_list, start=1):
            header = [
                f"## Chunk {index}",
                "",
                f"- **Chunk ID:** `{chunk.chunk_id}`",
                f"- **Layer:** {chunk.layer}",
                f"- **Tipe:** {chunk.chunk_type}",
                f"- **Halaman:** {self._page_label(chunk.page_start, chunk.page_end)}",
                "",
            ]
            markdown_parts.extend(header)
            markdown_parts.extend(_food_flag_markdown(chunk.metadata))
            markdown_parts.extend([chunk.content.strip(), ""])
        markdown_path = self._write_text(
            Path(output_dir) / "chunks.md",
            "\n".join(markdown_parts).rstrip() + "\n",
        )
        json_path = self._write_json(Path(output_dir) / "chunks.json", json_rows)
        return markdown_path, json_path

    def write_qa(self, output_dir: Path, pairs: Iterable[QaPair]) -> tuple[Path, Path]:
        pair_list = list(pairs)
        json_rows = [pair.to_payload() for pair in pair_list]
        markdown_parts: list[str] = ["# Hasil QA Generation", ""]
        for index, pair in enumerate(pair_list, start=1):
            markdown_parts.extend(
                [
                    f"## QA {index}",
                    "",
                    f"- **QA ID:** `{pair.qa_id}`",
                    f"- **Sumber Chunk:** `{pair.source_chunk_id}`",
                    "",
                    f"**Pertanyaan:** {pair.question.strip()}",
                    "",
                    f"**Jawaban:** {pair.answer.strip()}",
                    "",
                ]
            )
        markdown_path = self._write_text(
            Path(output_dir) / "qa.md",
            "\n".join(markdown_parts).rstrip() + "\n",
        )
        json_path = self._write_json(Path(output_dir) / "qa.json", json_rows)
        return markdown_path, json_path


    def write_chunk_payloads(self, output_dir: Path, payloads: Iterable[dict]) -> tuple[Path, Path]:
        rows = [dict(payload) for payload in payloads]
        markdown_parts: list[str] = ["# Hasil Chunking", ""]
        for index, payload in enumerate(rows, start=1):
            header = [
                f"## Chunk {index}",
                "",
                f"- **Chunk ID:** `{payload.get('chunk_id', '-')}`",
                f"- **Layer:** {payload.get('layer', '-')}",
                f"- **Tipe:** {payload.get('chunk_type', payload.get('type', '-'))}",
                f"- **Halaman:** {self._page_label(payload.get('page_start'), payload.get('page_end'))}",
                "",
            ]
            markdown_parts.extend(header)
            markdown_parts.extend(_food_flag_markdown(payload))
            markdown_parts.extend([str(payload.get("content") or "").strip(), ""])
        markdown_path = self._write_text(
            Path(output_dir) / "chunks.md",
            "\n".join(markdown_parts).rstrip() + "\n",
        )
        json_path = self._write_json(Path(output_dir) / "chunks.json", rows)
        return markdown_path, json_path

    def write_qa_payloads(self, output_dir: Path, payloads: Iterable[dict]) -> tuple[Path, Path]:
        rows = [dict(payload) for payload in payloads]
        markdown_parts: list[str] = ["# Hasil QA Generation", ""]
        for index, payload in enumerate(rows, start=1):
            markdown_parts.extend(
                [
                    f"## QA {index}",
                    "",
                    f"- **QA ID:** `{payload.get('qa_id', '-')}`",
                    f"- **Sumber Chunk:** `{payload.get('source_chunk_id', '-')}`",
                    "",
                    f"**Pertanyaan:** {str(payload.get('question') or '').strip()}",
                    "",
                    f"**Jawaban:** {str(payload.get('answer') or '').strip()}",
                    "",
                ]
            )
        markdown_path = self._write_text(
            Path(output_dir) / "qa.md",
            "\n".join(markdown_parts).rstrip() + "\n",
        )
        json_path = self._write_json(Path(output_dir) / "qa.json", rows)
        return markdown_path, json_path

    def ensure_extracted_markdown(self, output_dir: Path, chunk_payloads: Iterable[dict] = ()) -> Path:
        output_dir = Path(output_dir)
        target = output_dir / "extracted.md"
        if target.is_file():
            return target

        candidates = [
            path
            for path in output_dir.rglob("*.md")
            if path.name not in {"extracted.md", "chunks.md", "qa.md"}
            and path.is_file()
        ]
        if candidates:
            source = max(candidates, key=lambda path: path.stat().st_size)
            return self._write_text(target, source.read_text(encoding="utf-8", errors="replace"))

        rows = [dict(payload) for payload in chunk_payloads]
        layer_zero = [row for row in rows if int(row.get("layer", -1)) == 0]
        selected = layer_zero or rows
        parts = ["# Hasil Ekstraksi Dipulihkan dari Chunk", ""]
        for index, row in enumerate(selected, start=1):
            page = self._page_label(row.get("page_start"), row.get("page_end"))
            parts.extend([f"## Bagian {index} · Halaman {page}", "", str(row.get("content") or "").strip(), ""])
        return self._write_text(target, "\n".join(parts).rstrip() + "\n")

    def write_reindex_summary(
        self,
        output_dir: Path,
        *,
        source_id: str,
        source_name: str,
        collection_name: str,
        chunk_count: int,
        status: str,
    ) -> Path:
        payload = {
            "source_id": source_id,
            "source_name": source_name,
            "collection_name": collection_name,
            "chunk_count": int(chunk_count),
            "qa_count": 0,
            "status": status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._write_json(Path(output_dir) / "reindex_summary.json", payload)

    @staticmethod
    def list_artifacts(output_dir: Path) -> list[dict]:
        output_dir = Path(output_dir)
        result: list[dict] = []
        for name in ARTIFACT_FILENAMES:
            path = output_dir / name
            if path.is_file():
                result.append({"name": name, "size_bytes": path.stat().st_size, "path": str(path)})
        return result

    @classmethod
    def resolve_artifact(cls, output_dir: Path, filename: str, *, require_exists: bool = True) -> Path:
        if filename not in ARTIFACT_FILENAMES:
            raise ValueError("Nama artefak tidak diizinkan.")
        output_dir = Path(output_dir).resolve(strict=False)
        path = (output_dir / filename).resolve(strict=False)
        try:
            path.relative_to(output_dir)
        except ValueError as exc:
            raise ValueError("Path artefak tidak valid.") from exc
        if require_exists and not path.is_file():
            raise FileNotFoundError(filename)
        return path

    @classmethod
    def read_text(cls, output_dir: Path, filename: str) -> str:
        try:
            path = cls.resolve_artifact(output_dir, filename)
        except FileNotFoundError:
            return ""
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _elements_to_markdown(elements: Iterable[DocumentElement]) -> str:
        parts: list[str] = []
        for element in elements:
            content = element.content.strip()
            if not content:
                continue
            if element.element_type == "title":
                level = min(max(int(element.heading_level or 1), 1), 6)
                parts.extend([f"{'#' * level} {content}", ""])
            elif element.element_type == "code":
                parts.extend(["```", content, "```", ""])
            elif element.element_type == "image":
                parts.extend([f"> **Gambar halaman {element.page}**", "", content, ""])
            else:
                parts.extend([content, ""])
        return "\n".join(parts).rstrip() + "\n"

    @staticmethod
    def _page_label(page_start: int | None, page_end: int | None) -> str:
        if page_start is None and page_end is None:
            return "-"
        if page_start == page_end or page_end is None:
            return str(page_start)
        return f"{page_start}-{page_end}"

    @staticmethod
    def _write_text(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        return path

    @classmethod
    def _write_json(cls, path: Path, payload) -> Path:
        return cls._write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        )


def render_markdown_safe(markdown_text: str) -> str:
    """Render subset Markdown menjadi HTML aman tanpa mengizinkan HTML mentah."""

    lines = str(markdown_text or "").splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    index = 0
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(part.strip() for part in paragraph if part.strip())
            if text:
                output.append(f"<p>{_inline_markdown(text)}</p>")
            paragraph.clear()

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(raw)
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            output.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
            index += 1
            continue

        if _is_table_header(lines, index):
            flush_paragraph()
            headers = _table_cells(lines[index])
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_table_cells(lines[index]))
                index += 1
            head_html = "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in headers)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            output.append(f"<div class=\"markdown-table-wrap\"><table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>")
            continue

        if re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            items: list[str] = []
            while index < len(lines):
                match = re.match(r"^\s*[-*+]\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(match.group(1))
                index += 1
            output.append("<ul>" + "".join(f"<li>{_inline_markdown(item)}</li>" for item in items) + "</ul>")
            continue

        if re.match(r"^\d+[.)]\s+", stripped):
            flush_paragraph()
            items = []
            while index < len(lines):
                match = re.match(r"^\s*\d+[.)]\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(match.group(1))
                index += 1
            output.append("<ol>" + "".join(f"<li>{_inline_markdown(item)}</li>" for item in items) + "</ol>")
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].strip())
                index += 1
            output.append(f"<blockquote>{_inline_markdown(' '.join(quote_lines))}</blockquote>")
            continue

        paragraph.append(raw)
        index += 1

    flush_paragraph()
    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(output)


def _inline_markdown(value: str) -> str:
    escaped = html.escape(str(value), quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_header(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return False
    separator = lines[index + 1].strip().strip("|")
    cells = [cell.strip() for cell in separator.split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)
