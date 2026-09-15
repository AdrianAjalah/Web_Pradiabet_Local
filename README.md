# PrediBeat

PrediBeat adalah aplikasi web FastAPI untuk assessment, meal plan, progress tracker, chatbot nutrisi, dan Hybrid RAG dokumen. Versi repository ini memakai model lokal melalui Ollama.

## Buku panduan

[**Unduh Manual Book PrediaBeat V1 (Word)**](docs/manual-book-predibeat-v1.docx?raw=true)

[**Unduh Manual Book PrediaBeat (PDF)**](docs/manual-book-predibeat.pdf?raw=true)

Manual Book PrediaBeat V1 berisi panduan penggunaan, perhitungan kesehatan, meal plan personal, progress tracker, chatbot, ERD, flowchart, pengelolaan data, instalasi, dan pembaruan Docker.

## **Score Risiko Diabetes**

Score risiko dihitung dari profil kesehatan dan kebiasaan pengguna. Hasil laboratorium memiliki prioritas:

- GDP ≥126 mg/dL atau HbA1c ≥6,5%: **Diabetes Terkonfirmasi**, score 100.
- GDP 100–125 mg/dL atau HbA1c 5,7–<6,5%: **Prediabetes Terkonfirmasi**, score 75.

Jika hasil laboratorium tidak langsung menentukan kategori, aplikasi menjumlahkan faktor berikut:

| Faktor | Kondisi | Score |
|---|---|---:|
| Usia | 35–44 / 45–54 / ≥55 tahun | +3 / +5 / +8 |
| Riwayat keluarga diabetes | Ada | +20 |
| BMI | 23–<25 / ≥25 | +10 / +15 |
| Lingkar pinggang | Laki-laki ≥90 cm atau perempuan ≥80 cm | +15 |
| Minuman manis | 3–5 kali / sering atau setiap hari | +10 / +15 |
| Porsi nasi | 2 porsi / lebih dari 2 porsi per hari | +5 / +10 |
| Duduk atau rebahan | Lebih dari 6 atau 8 jam sesuai pilihan formulir | +10 |
| Olahraga | Tidak pernah / aktif 3–4 kali atau 5 hari | +5 / −5 |
| Tidur | Kurang dari 5 atau 6 jam sesuai pilihan formulir | +5 |
| Gejala klasik | Haus, sering kencing, sering lapar, atau kesemutan | +5 per gejala |
| Luka sulit sembuh | Dipilih pada profil | +8 |
| Kondisi penyerta | Hipertensi, PCOS, atau kolesterol | +10 |
| Riwayat gestasional atau gula darah | Tercatat pada profil | +15 |

Kategori score akhir:

| Score | Kategori |
|---:|---|
| 0–24 | Rendah (Aman) |
| 25–49 | Sedang (Waspada) |
| ≥50 | Tinggi (Sangat Berisiko Prediabetes) |

Score ini merupakan hasil skrining aplikasi dan bukan diagnosis medis.

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
