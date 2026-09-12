# Optimasi latensi chatbot

Alur: validasi dan konfirmasi tindakan → parser cepat jika pola jelas → planner
Ollama untuk pesan lain → konteks profil/tool/PDF → jawaban Ollama → simpan riwayat.

- Sapaan persis dan lookup nutrisi sederhana hanya memakai satu panggilan model.
  Angka/porsi, kata rujukan, permintaan gabungan dan pola tidak dikenal tetap memakai planner AI.
- Riwayat prompt dibatasi total 4.000 karakter, mengutamakan pesan terbaru.
  Profil dan hasil tool tetap dipertahankan; sapaan tidak mengambil profil/progress.
  Batas data terverifikasi tetap 14.000 karakter seperti sebelumnya.
- `CHATBOT_HISTORY_CHARS=4000` dan `CHATBOT_KEEP_ALIVE=10m` dapat diatur lewat
  environment proses aplikasi. Keep-alive berlaku pada model chatbot; membutuhkan memori
  yang cukup dan tidak menjamin model tetap resident saat server kekurangan memori.
- Halaman chatbot mengirim `stream: true` ke POST `/tanya`, menerima NDJSON
  `delta`, lalu `done` dengan jawaban lengkap dan metadata. Respons tindakan tetap JSON.
  Klien tanpa flag mendapat JSON biasa, sehingga benchmark lama tetap kompatibel.
- Streaming terputus menghasilkan event error, tidak menyimpan jawaban parsial
  sebagai percakapan selesai, dan tidak mencoba ulang otomatis. Browser mencegah
  pengiriman ganda selama satu pesan berlangsung.
- Respons menyertakan `timings`: planner_ms, context_ms, answer_ms, total_ms,
  serta first_token_ms untuk streaming. Ini waktu aplikasi, bukan waktu jaringan browser.
  Log Ollama mencatat load_duration, prompt_eval_duration, eval_duration (nanodetik)
  dan jumlah token tanpa mencatat isi percakapan.

Restart proses aplikasi setelah perubahan. Bila menggunakan Docker, rebuild image
aplikasi dengan alur deployment proyek. Pastikan reverse proxy tidak membuffer NDJSON;
respons sudah menyertakan `X-Accel-Buffering: no` dan `Cache-Control: no-cache`.

Bandingkan benchmark dengan model/hardware/pertanyaan yang sama, pisahkan warm-up
dan permintaan berikutnya. Skrip `scripts/benchmark_chatbot_latency.py` mengukur waktu
jawaban lengkap. Ukur kemunculan teks pertama melalui halaman chatbot untuk streaming.
Periksa `ollama ps` pada server model untuk memastikan penggunaan GPU. Tidak ada
perubahan otomatis pada model, konfigurasi GPU, atau layanan Ollama.

## Verifikasi Docker 12 September 2026

Container web telah dibangun ulang. Runtime lokal menggunakan
`OLLAMA_BASE_URL=http://host.docker.internal:11434`; alamat sebelumnya port 11435
tidak memiliki tunnel aktif. Web dan rag-worker sudah dibuat ulang dengan alamat baru.
Model tetap llama3.1:8b Q4_K_M, context_length 4096. API Ollama melaporkan ukuran
model resident 5.61 GB, termasuk sekitar 4.23 GB di VRAM.

Hasil satu kali pengukuran tiap skenario melalui endpoint HTTP `/tanya`:

| Skenario | Teks pertama | Jawaban selesai |
| --- | ---: | ---: |
| Sapaan, model belum dimuat | 55.722 dtk | 59.221 dtk |
| Sapaan berikutnya | 0.170 dtk | 3.369 dtk |
| Kalori nasi goreng, streaming | 3.466 dtk | 6.029 dtk |
| Perbandingan dua makanan, JSON biasa | Tidak diukur | 13.411 dtk |

Keempat respons berasal dari Ollama, bukan fallback. Akun/profil sintetis untuk
pengujian sudah dihapus; tidak memakai akun pengguna yang sudah ada.
Data mentah tersimpan di `docs/chatbot-runtime-report.json`. Skrip pengujian ada
di `scripts/verify_chatbot_runtime.py`, dijalankan dalam container dengan PYTHONPATH=/app.

Log menunjukkan permintaan pertama menghabiskan 39.032 detik untuk memuat model,
16.202 detik untuk evaluasi prompt, dan 3.511 detik untuk generasi. Pada sapaan
berikutnya, pemuatan hanya 0.024 detik. Keep-alive membantu selama model tetap
resident; bukan jaminan respons pertama cepat setelah idle atau restart Ollama.
Angka ini bukan perbandingan sebelum/sesudah optimasi atau benchmark statistik.
