import json
from pathlib import Path

from app.rag.extractors.pdf_extractor import MinerUPdfExtractor


def test_parse_content_list_maps_text_table_and_image(tmp_path: Path):
    content_file = tmp_path / "sample_content_list.json"
    content_file.write_text(
        json.dumps(
            [
                {"type": "text", "text": "BAB 1", "text_level": 1, "page_idx": 0, "bbox": [0, 0, 1, 1]},
                {"type": "text", "text": "Isi paragraf", "page_idx": 0},
                {"type": "table", "table_body": "|A|B|", "page_idx": 1},
                {"type": "image", "img_path": "images/a.png", "image_caption": ["Grafik gula"], "page_idx": 1},
            ]
        ),
        encoding="utf-8",
    )

    elements = MinerUPdfExtractor.parse_content_list(content_file)

    assert [item.element_type for item in elements] == ["title", "text", "table", "image"]
    assert elements[0].heading_level == 1
    assert elements[2].content == "|A|B|"
    assert "Grafik gula" in elements[3].content
    assert elements[0].page == 1


def test_find_content_list_prefers_legacy_content_list(tmp_path: Path):
    (tmp_path / "x_content_list_v2.json").write_text("[]")
    expected = tmp_path / "x_content_list.json"
    expected.write_text("[]")

    assert MinerUPdfExtractor.find_content_list(tmp_path) == expected
