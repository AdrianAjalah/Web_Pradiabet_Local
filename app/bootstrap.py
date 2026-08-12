"""Factory dependency runtime untuk web dan worker."""
from __future__ import annotations

from app.core.config import Settings
from app.rag.chunkers.csv_two_layer_chunker import CsvTwoLayerChunker
from app.rag.chunkers.pdf_hierarchical_chunker import PdfHierarchicalChunker
from app.rag.clients.factory import build_text_generation_client
from app.rag.clients.ollama_client import OllamaHttpClient
from app.rag.embeddings.factory import build_embedder
from app.rag.extractors.fallback_pdf_extractor import FallbackPdfExtractor
from app.rag.extractors.image_describer import OllamaImageDescriber
from app.rag.extractors.pdf_extractor import MinerUPdfExtractor
from app.rag.extractors.pypdf_extractor import PyPdfTextExtractor
from app.rag.pipelines.csv_pipeline import CsvIngestionPipeline
from app.rag.pipelines.pdf_pipeline import PdfIngestionPipeline
from app.rag.qa.pdf_qa_generator import PdfQaGenerator
from app.rag.retrieval.food_retriever import FoodRetriever
from app.rag.retrieval.pdf_retriever import PdfRetriever
from app.rag.vectorstores.qdrant_store import CollectionNames, QdrantVectorStore
from app.services.document_summary_service import DocumentSummaryService
from app.services.rag_artifact_service import RagArtifactWriter


def build_runtime():
    from qdrant_client import QdrantClient

    settings = Settings()
    text_client = build_text_generation_client(settings)
    embedder = build_embedder(settings)
    qdrant = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=60,
    )
    collections = CollectionNames(
        settings.pdf_chunks_collection,
        settings.pdf_qa_collection,
        settings.food_chunks_collection,
    )
    store = QdrantVectorStore(qdrant, collections, settings.vector_size)
    store.ensure_collections()
    return settings, text_client, embedder, qdrant, collections, store


def build_pipelines():
    settings, text_client, embedder, _qdrant, _collections, store = build_runtime()
    artifact_writer = RagArtifactWriter()
    image_describer = None
    if isinstance(text_client, OllamaHttpClient):
        image_describer = OllamaImageDescriber(text_client, model=settings.vision_model)
    pdf_pipeline = PdfIngestionPipeline(
        extractor=FallbackPdfExtractor(
            MinerUPdfExtractor(
                command=settings.mineru_command,
                backend=settings.mineru_backend,
                method=settings.mineru_method,
            ),
            PyPdfTextExtractor(),
            enabled=settings.mineru_fallback_pypdf,
        ),
        chunker=PdfHierarchicalChunker(
            max_tokens=settings.pdf_chunk_max_tokens,
            overlap_tokens=settings.pdf_chunk_overlap_tokens,
        ),
        qa_generator=PdfQaGenerator(text_client, model=settings.qa_model),
        embedder=embedder,
        store=store,
        summarizer=DocumentSummaryService(text_client, model=settings.qa_model),
        image_describer=image_describer,
        artifact_writer=artifact_writer,
    )
    csv_pipeline = CsvIngestionPipeline(CsvTwoLayerChunker(), embedder, store, artifact_writer=artifact_writer)
    return settings, pdf_pipeline, csv_pipeline


def build_retrievers():
    _settings, _text_client, embedder, qdrant, collections, _store = build_runtime()
    return (
        PdfRetriever(qdrant, embedder, collections),
        FoodRetriever(qdrant, embedder, collections.food_chunks),
    )


def build_pdf_retriever():
    """Build only the PDF retriever used by the V3 chatbot."""
    from qdrant_client import QdrantClient

    settings = Settings()
    embedder = build_embedder(settings)
    qdrant = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=60,
    )
    collections = CollectionNames(
        settings.pdf_chunks_collection,
        settings.pdf_qa_collection,
        settings.food_chunks_collection,
    )
    return PdfRetriever(qdrant, embedder, collections)
