# Dataset Referensi PrediBeat

Folder ini menyimpan **dataset utama yang mempunyai lokasi tetap**. Dataset di sini
berbeda dari `data/rag/inbox`, karena file pada inbox hanya antrean sementara yang
akan dipindahkan oleh RAG worker setelah selesai diproses.

## Struktur

```text
data/reference/
├── food/
│   └── master_makanan_kategori_flag_mealplan.csv
├── diets/
│   └── NutrinusaDatabase_InformationDiet.csv
└── backups/
    └── .gitkeep
```

### `food/master_makanan_kategori_flag_mealplan.csv`

- Dataset aktif makanan dan nilai gizi.
- Digunakan oleh meal plan, rekomendasi makanan, dan food retrieval.
- Diproses menjadi dua layer chunk.
- Embedding menggunakan `bge-m3` melalui tunnel HPC.
- Disimpan ke collection Qdrant `predibeat_food_chunks`.
- Tidak dibuatkan QA.
- Penilaian gula menggunakan `gula_g`; kategori buah diberi interpretasi gula alami buah.

### `diets/NutrinusaDatabase_InformationDiet.csv`

- Referensi deskripsi dan aturan berbagai jenis diet.
- Dibaca langsung oleh service rekomendasi diet/dashboard.
- Tidak masuk ke collection makanan Qdrant.
- Tidak melewati MinerU dan tidak dibuatkan QA.

### `backups/`

Setiap admin mengganti dataset melalui dashboard, file lama disalin otomatis ke
folder ini sebelum file baru diaktifkan. Backup runtime tidak dikomit ke Git.

## Dashboard admin

Buka:

```text
http://localhost:8000/admin/datasets
```

Dashboard menampilkan jumlah baris, kolom, ukuran file, delimiter, lokasi aktif,
form upload pengganti, dan tombol reindex untuk dataset makanan.
