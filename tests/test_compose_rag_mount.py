from pathlib import Path


def test_web_and_worker_share_host_rag_directory():
    compose = Path('docker-compose.yml').read_text(encoding='utf-8')
    assert compose.count('- ./data/rag:/app/data/rag') == 2
