from app.rag.vectorstores.qdrant_store import CollectionNames, deterministic_point_id


def test_collection_names_are_isolated():
    names = CollectionNames("pdf_chunks", "pdf_qa", "food_chunks")
    assert len({names.pdf_chunks, names.pdf_qa, names.food_chunks}) == 3


def test_deterministic_point_id_is_stable_uuid_string():
    first = deterministic_point_id("doc:chunk:1")
    second = deterministic_point_id("doc:chunk:1")
    assert first == second
    assert len(first) == 36
