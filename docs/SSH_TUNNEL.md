# SSH Tunnel Ollama HPC

## Tujuan

Model berikut tetap berada di HPC perusahaan:

- `bge-m3` untuk seluruh embedding;
- `llama3.1:8b` untuk QA PDF dan ringkasan;
- `llava` untuk deskripsi gambar.

Docker tidak menjalankan ketiga model itu. Komputer host membuka tunnel SSH, lalu
container worker mengakses port host.

## Pemetaan port

```text
RAG worker container
http://host.docker.internal:11435
              │
              ▼
Laptop/host localhost:11435
              │ SSH -L
              ▼
HPC 127.0.0.1:11434 (Ollama)
```

## Windows PowerShell

```powershell
.\scripts\open_hpc_tunnel.ps1 `
  -SshUser "nama_user" `
  -SshHost "alamat-hpc" `
  -SshPort 22
```

Perintah ekuivalen:

```powershell
ssh -p 22 -N `
  -L 11435:127.0.0.1:11434 `
  -o ServerAliveInterval=30 `
  -o ServerAliveCountMax=3 `
  nama_user@alamat-hpc
```

Terminal ini terlihat diam ketika tunnel berhasil. Jangan ditutup selama worker
memerlukan Ollama.

## Menguji tunnel dari host

```powershell
Invoke-RestMethod http://localhost:11435/api/tags
```

Menguji embedding:

```powershell
$body = @{
  model = "bge-m3"
  input = @("tes embedding PrediBeat")
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:11435/api/embed `
  -ContentType "application/json" `
  -Body $body
```

## Menguji dari container

```powershell
docker compose exec rag-worker python -c `
  "import requests; print(requests.get('http://host.docker.internal:11435/api/tags', timeout=10).status_code)"
```

Hasil yang diharapkan: `200`.

## Memastikan model tersedia di HPC

Jalankan pada HPC:

```bash
ollama list
```

Pastikan ada:

```text
bge-m3
llama3.1:8b
llava
```

Bila belum ada dan Anda memiliki izin:

```bash
ollama pull bge-m3
ollama pull llama3.1:8b
ollama pull llava
```

## Masalah umum

### Container tidak bisa memakai `localhost:11435`

Di dalam container, `localhost` berarti container itu sendiri. Karena tunnel berada
di laptop/host, `.env` harus menggunakan:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11435
```

### Tunnel terputus ketika idle

Script sudah memakai:

```text
ServerAliveInterval=30
ServerAliveCountMax=3
```

Namun VPN, firewall, atau kebijakan HPC tetap dapat memutus sesi. Worker akan
menandai job gagal setelah retry. Buka kembali tunnel lalu upload ulang/retry job.

### Port 11435 sudah dipakai

Periksa:

```powershell
Get-NetTCPConnection -LocalPort 11435 -ErrorAction SilentlyContinue
```

Gunakan port lain, misalnya 11436, lalu ubah parameter tunnel dan `.env`.

### Ollama hanya listen pada interface tertentu

Forward memakai `127.0.0.1:11434` dari sisi HPC. Ini cocok bila Ollama hanya listen
lokal, karena SSH server membuat koneksi dari mesin HPC itu sendiri.
