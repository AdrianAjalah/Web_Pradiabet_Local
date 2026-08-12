"""Adapter MinerU CLI untuk mengekstrak PDF menjadi elemen terstruktur."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.rag.domain.models import DocumentElement


class MinerUExtractionError(RuntimeError):
    pass


class MinerUPdfExtractor:
    def __init__(
        self,
        command: str = "mineru",
        backend: str = "pipeline",
        method: str = "auto",
        timeout_seconds: int = 3600,
    ) -> None:
        self.command = command
        self.backend = backend
        self.method = method
        self.timeout_seconds = timeout_seconds

    def extract(self, source_path: Path, output_dir: Path) -> list[DocumentElement]:
        source_path = Path(source_path)
        output_dir = Path(output_dir)
        if source_path.suffix.lower() != ".pdf":
            raise ValueError("MinerU extractor hanya menerima file PDF.")
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            self.command,
            "-p",
            str(source_path),
            "-o",
            str(output_dir),
            "-b",
            self.backend,
            "-m",
            self.method,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise MinerUExtractionError(
                f"MinerU gagal untuk {source_path.name}: {completed.stderr.strip() or completed.stdout.strip()}"
            )

        content_list = self.find_content_list(output_dir)
        return self.parse_content_list(content_list)

    @staticmethod
    def find_content_list(output_dir: Path) -> Path:
        output_dir = Path(output_dir)
        legacy = sorted(output_dir.rglob("*_content_list.json"))
        if legacy:
            return legacy[0]
        v2 = sorted(output_dir.rglob("*_content_list_v2.json"))
        if v2:
            return v2[0]
        raise MinerUExtractionError(f"MinerU tidak menghasilkan content_list JSON di {output_dir}")

    @classmethod
    def parse_content_list(cls, content_file: Path) -> list[DocumentElement]:
        raw: Any = json.loads(Path(content_file).read_text(encoding="utf-8"))
        items = cls._flatten_v2(raw) if raw and isinstance(raw, list) and isinstance(raw[0], list) else raw
        elements: list[DocumentElement] = []
        for index, item in enumerate(items or []):
            if not isinstance(item, dict):
                continue
            element = cls._map_item(item, index=index, base_dir=Path(content_file).parent)
            if element and element.content.strip():
                elements.append(element)
        return elements

    @staticmethod
    def _flatten_v2(raw: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        for page_idx, page_items in enumerate(raw):
            for item in page_items:
                copied = dict(item)
                copied.setdefault("page_idx", page_idx)
                flattened.append(copied)
        return flattened

    @classmethod
    def _map_item(cls, item: dict[str, Any], index: int, base_dir: Path) -> DocumentElement | None:
        raw_type = str(item.get("type") or "text").lower()
        page = int(item.get("page_idx") or 0) + 1
        heading_level = item.get("text_level")
        content = ""
        image_path: str | None = None

        if raw_type in {"text", "title"}:
            content = cls._extract_text(item)
            if raw_type == "title" or heading_level not in (None, 0, "0"):
                element_type = "title"
                try:
                    heading_level = int(heading_level or item.get("content", {}).get("level") or 1)
                except (TypeError, ValueError):
                    heading_level = 1
            else:
                element_type = "text"
        elif raw_type == "table":
            element_type = "table"
            content = str(item.get("table_body") or item.get("content") or "")
        elif raw_type in {"image", "chart"}:
            element_type = "image"
            relative = item.get("img_path") or item.get("image_path")
            image_path = str((base_dir / relative).resolve()) if relative else None
            captions = item.get("image_caption") or item.get("chart_caption") or []
            if isinstance(captions, str):
                captions = [captions]
            generated = item.get("content")
            content = "\n".join([*(str(x) for x in captions), str(generated or "")]).strip()
            if not content:
                content = f"Gambar pada halaman {page}"
        elif raw_type in {"equation", "code", "list"}:
            element_type = raw_type
            content = cls._extract_text(item)
        else:
            return None

        return DocumentElement(
            element_id=f"element-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, content or str(index))}",
            element_type=element_type,
            content=content.strip(),
            page=page,
            heading_level=heading_level if isinstance(heading_level, int) else None,
            bbox=item.get("bbox"),
            image_path=image_path,
            metadata={"mineru_type": raw_type},
        )

    @staticmethod
    def _extract_text(item: dict[str, Any]) -> str:
        for key in ("text", "content", "code_body", "list_items"):
            value = item.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "\n".join(str(part) for part in value)
            if isinstance(value, dict):
                fragments: list[str] = []
                for nested in value.values():
                    if isinstance(nested, str):
                        fragments.append(nested)
                    elif isinstance(nested, list):
                        for part in nested:
                            if isinstance(part, str):
                                fragments.append(part)
                            elif isinstance(part, dict) and part.get("content"):
                                fragments.append(str(part["content"]))
                if fragments:
                    return "\n".join(fragments)
        return ""
