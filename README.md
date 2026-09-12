# PrediBeat

PrediBeat adalah aplikasi web FastAPI untuk assessment, meal plan, progress tracker, chatbot nutrisi, dan Hybrid RAG dokumen. Versi repository ini memakai model lokal melalui Ollama.

## Buku panduan

[**Unduh Manual Book PrediBeat (PDF)**](docs/manual-book-predibeat.pdf?raw=true)

Panduan 9 halaman berisi cara menggunakan aplikasi dan chatbot, mengelola dokumen, memperbarui aplikasi melalui Docker, serta mengatasi kendala umum.

## Model AI

- LLM: `llama3.1:8b` melalui Ollama.
- Embedding: `bge-m3` melalui Ollama.
- Vision: `llava` melalui Ollama bila deskripsi gambar PDF diperlukan.
- LLM dan embedding tidak menggunakan provider cloud pada runtime.

## Komponen utama

- FastAPI + Jinja2 untuk aplikasi web.
- PostgreSQL untuk data aplikasi dan job RAG.
- MinerU untuk ekstraksi PDF.
- Qdrant untuk vector store PDF dan QA. Qdrant dapat dijalankan lokal atau pada server terpisah.
- Dataset makanan dan diet pada `data/reference/`.

## Menjalankan project

1. Salin `.env.example` menjadi `.env`.
2. Isi konfigurasi database, Ollama, Qdrant, dan secret autentikasi.
3. Pastikan model `bge-m3`, `llama3.1:8b`, dan `llava` tersedia pada Ollama.
4. Jalankan layanan dengan Docker Compose.

```bash
docker compose up -d --build
```

Untuk Ollama yang berada di HPC atau server lain, gunakan script tunnel pada folder `scripts/`.

## Testing

```bash
pytest -q
```

## Struktur penting

```text
app/                 source utama FastAPI dan business logic
app/rag/             ekstraksi, chunking, embedding, retrieval, vector store
worker/              worker pemrosesan job RAG
data/reference/      dataset referensi
data/rag/             folder runtime RAG, isi runtime tidak dikomit
scripts/              benchmark dan helper SSH tunnel
tests/                automated tests
docs/                 dokumentasi operasi dan alur RAG
```

## Keamanan repository

File `.env`, database lokal, output RAG, file inbox, cache Python, dan backup runtime tidak boleh dikomit. Aturan tersebut sudah disiapkan pada `.gitignore`.
