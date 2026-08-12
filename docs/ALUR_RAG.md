# Alur RAG PrediBeat V2

## A. Alur upload dan antrean

```text
Admin upload file
       │
       ▼
FastAPI memvalidasi PDF/CSV
       │
       ├─ simpan file ke data/rag/inbox
       └─ insert rag_jobs(status=pending)
                       │
                       ▼
              rag-worker claim job
              status=processing
```

Web tidak menjalankan ekstraksi di `BackgroundTasks`. Job berada di PostgreSQL,
sehingga status tidak hilang ketika web restart.

## B. Alur PDF

```text
PDF
 │
 ▼
MinerU pipeline lokal
 │
 ├─ content_list JSON
 ├─ Markdown
 ├─ gambar/crop
 └─ metadata halaman/bbox
 │
 ▼
DocumentElement
 │
 ├─ title
 ├─ text
 ├─ table
 ├─ image/chart
 ├─ equation
 └─ list/code
 │
 ├──────────────► LLaVA via tunnel bila gambar perlu deskripsi
 │
 ▼
Ringkasan dokumen dengan llama3.1:8b
 │
 ▼
Hierarchical chunking
 ├─ Layer 0 element
 ├─ Layer 1 section
 ├─ Layer 2 page
 └─ Layer 3 document summary
 │
 ▼
Embedding seluruh chunk dengan bge-m3 via tunnel
 │
 ▼
predibeat_pdf_chunks (Qdrant Cloud)
 │
 ▼
QA generator llama3.1:8b
 │
 ▼
Embedding QA dengan bge-m3
 │
 ▼
predibeat_pdf_qa (Qdrant Cloud)
```

### Mengapa empat layer?

- Layer 0 baik untuk jawaban sangat spesifik.
- Layer 1 memberi konteks subbab.
- Layer 2 menjaga konteks halaman, termasuk tabel/gambar di halaman yang sama.
- Layer 3 membantu pertanyaan umum tentang isi dokumen.

### Batas chunk

Default:

```text
PDF_CHUNK_MAX_TOKENS=900
PDF_CHUNK_OVERLAP_TOKENS=100
```

Nilai dapat diubah dari `.env`. Splitter memakai estimasi token ringan agar tidak
memuat tokenizer model besar hanya untuk chunking.

### QA PDF

QA hanya dibuat dari layer 0/1/2 yang memiliki informasi faktual. Setiap QA
menyimpan `source_chunk_id`, sehingga jawaban dapat ditelusuri kembali ke chunk
sumber dan halaman.

## C. Alur CSV

```text
CSV
 │
 ▼
Python csv parser langsung
 │
 ├─ normalisasi header/nilai
 └─ satu row = satu item makanan
 │
 ▼
Two-layer chunking
 ├─ Layer 0 food/item detail
 └─ Layer 1 category summary
 │
 ▼
Embedding bge-m3 via tunnel
 │
 ▼
predibeat_food_chunks (Qdrant Cloud)
```

CSV tidak menjalankan:

- MinerU;
- ekstraksi gambar PDF;
- ringkasan dokumen Llama;
- QA generator.

Hasil `qa_count` CSV selalu `0`.

## D. Retrieval chatbot

### Pertanyaan edukasi dari PDF

1. Embed pertanyaan dengan BGE-M3.
2. Cari pada `predibeat_pdf_qa` dan `predibeat_pdf_chunks`.
3. Gabungkan hasil berdasarkan score.
4. Berikan konteks terpilih ke model jawaban chatbot.

### Pertanyaan makanan

1. Coba exact match `food_name`.
2. Bila tidak ada, gunakan vector search.
3. Gunakan metadata nutrisi dari payload.
4. Jangan mengarang makanan yang tidak tersedia.

### Aturan gula

- Gunakan `gula_g` sebagai nilai gula pembahasan/scoring.
- Buah mendapat keterangan gula alami.
- Buah tidak dipenalti seperti minuman manis, snack, dessert, atau ultra-proses.

## E. Collection Qdrant

### `predibeat_pdf_chunks`

Payload utama:

```json
{
  "source_id": "uuid",
  "source_name": "pedoman.pdf",
  "source_type": "pdf",
  "chunk_id": "chunk-...",
  "layer": 1,
  "chunk_type": "section",
  "page_start": 3,
  "page_end": 5,
  "parent_chunk_id": null,
  "content": "..."
}
```

### `predibeat_pdf_qa`

```json
{
  "source_type": "pdf_qa",
  "source_chunk_id": "chunk-...",
  "question": "...",
  "answer": "...",
  "content": "Pertanyaan: ... Jawaban: ..."
}
```

### `predibeat_food_chunks`

```json
{
  "source_type": "csv",
  "layer": 0,
  "chunk_type": "food_item",
  "food_name": "apel",
  "food_category": "Buah",
  "gula_g": "...",
  "content": "..."
}
```

## F. Penanganan kegagalan

- MinerU gagal → job `failed`, file pindah ke `data/rag/failed`.
- Ollama tunnel putus → HTTP client retry terbatas lalu job gagal dengan pesan.
- Qdrant gagal → job gagal; file tidak ditandai processed.
- CSV invalid/kosong → pipeline melempar error dan job masuk failed.
- Web restart → job tetap berada di PostgreSQL.

Tahap pengembangan selanjutnya dapat menambahkan tombol retry yang membuat job baru
atau mengembalikan job failed ke pending setelah masalah diperbaiki.
