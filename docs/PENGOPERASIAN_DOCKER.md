# Pengoperasian Docker PrediBeat V2

## Service

```text
db                       PostgreSQL
web                      FastAPI ringan
rag-worker               MinerU + pipeline ingestion
mineru-models-download   setup model satu kali
```

## Build

```powershell
docker compose build
```

Image `web` tidak membawa MinerU. Image `rag-worker` lebih besar karena memuat
MinerU dan dependency pemrosesan PDF.

## Download model MinerU

```powershell
docker compose --profile setup run --rm mineru-models-download
```

Model masuk ke volume `mineru_home`. Periksa volume:

```powershell
docker volume ls
```

## Start

```powershell
docker compose up -d db web rag-worker
```

## Status

```powershell
docker compose ps
```

## Log

```powershell
docker compose logs -f web
docker compose logs -f rag-worker
docker compose logs -f db
```

## Stop tanpa menghapus data

```powershell
docker compose down
```

## Stop dan hapus seluruh volume

```powershell
docker compose down -v
```

Perintah `-v` menghapus PostgreSQL, file RAG, dan model MinerU. Jangan gunakan pada
produksi tanpa backup.

## Rebuild hanya web

```powershell
docker compose build web
docker compose up -d web
```

## Rebuild worker

```powershell
docker compose build rag-worker
docker compose up -d rag-worker
```

Volume model tetap dipertahankan.

## Pembatasan resource opsional

Pada Docker Compose lokal, resource dapat dibatasi untuk mencegah MinerU memakai
seluruh RAM/CPU. Contoh yang dapat ditambahkan pada `rag-worker`:

```yaml
mem_limit: 8g
cpus: 4
```

Nilainya harus disesuaikan dengan perangkat. Batas terlalu kecil dapat membuat
MinerU gagal pada PDF besar.

## Backup volume

### PostgreSQL

```powershell
docker compose exec -T db pg_dump `
  -U predibeat predibeat > predibeat_backup.sql
```

### Data RAG

Karena named volume tidak tampak sebagai folder Windows biasa, backup dapat dibuat
dengan container sementara atau mengubah Compose menjadi bind mount. Untuk data
rahasia perusahaan, tentukan kebijakan retensi dan enkripsi terlebih dahulu.
