from app.rag.clients.ollama_client import OllamaHttpClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        if url.endswith("/api/embed"):
            return FakeResponse({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
        return FakeResponse({"message": {"content": "jawaban"}})


def test_embed_uses_bge_m3_batch_endpoint():
    session = FakeSession()
    client = OllamaHttpClient("http://tunnel:11435", session=session)

    vectors = client.embed(["a", "b"], model="bge-m3")

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert session.calls[0][1] == {"model": "bge-m3", "input": ["a", "b"]}


def test_chat_uses_requested_model():
    session = FakeSession()
    client = OllamaHttpClient("http://tunnel:11435", session=session)

    answer = client.chat("jelaskan", model="llama3.1:8b")

    assert answer == "jawaban"
    assert session.calls[0][1]["model"] == "llama3.1:8b"


def test_chat_supports_json_format_and_temperature_zero():
    session = FakeSession()
    client = OllamaHttpClient("http://tunnel:11435", session=session)

    answer = client.chat(
        "klasifikasikan",
        model="llama3.1:8b",
        format="json",
        temperature=0,
    )

    assert answer == "jawaban"
    payload = session.calls[0][1]
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0
