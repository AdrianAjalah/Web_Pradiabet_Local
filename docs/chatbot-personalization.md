# Rekomendasi personal chatbot

## Membaca profil

Perintah seperti "cek profil kesehatan saya", "lihat profil saya", atau "berapa berat badan saya" membaca profil akun yang sedang login langsung dari database. Jawaban menampilkan data diri, pantangan, hasil lab yang diinput, kategori risiko hasil assessment tersimpan, target nutrisi dan jadwal. Nilai yang belum tersedia dinyatakan "Belum diisi". Jalur ini tidak memakai LLM untuk mengisi nilai atau menentukan diagnosis; ID akun berasal dari sesi autentikasi, bukan isi pesan atau parameter pengguna.

Rekomendasi makanan mengambil meal plan aktif milik pengguna yang login. Permintaan makan siang hanya menampilkan slot siang; permintaan umum menampilkan jadwal yang tersimpan. Jika menu tidak tersedia, chatbot menyampaikan keterbatasannya tanpa membuat daftar makanan dari urutan kalori terendah.

## Kandidat pengganti

- Cari menu lain memanggil generator meal plan backend dalam mode preview tanpa menyimpan profil.
- Untuk permintaan satu jadwal, hanya slot tersebut diganti; total sehari dievaluasi kembali.
- Sebagian makanan boleh tetap sama. Sistem mencoba sampai enam kandidat dan menghindari susunan yang sama dengan menu aktif atau kandidat terdahulu yang masih diingat.
- Pakai menu ini menyimpan kandidat persis seperti yang ditampilkan. Tetap pakai menu sebelumnya membatalkan kandidat.
- Kandidat mengikuti masa berlaku konfirmasi 10 menit. Profil atau menu yang berubah membuat kandidat lama tidak dapat disimpan.
- Riwayat susunan kandidat dibatasi 40 entri dan hanya berada dalam memori proses, seperti konfirmasi chatbot lainnya. Restart menghapus kandidat.

Generator lama memilih menu terdekat dengan target jika toleransi makro belum terpenuhi. Preview menyatakan kondisi ini secara eksplisit dan menolak kandidat yang melampaui batas gula tambahan atau natrium harian. Tidak ada klaim bahwa setiap kandidat pasti memenuhi seluruh target.

## Pemeriksaan makanan

Pertanyaan boleh/aman makan membersihkan pengulangan kata perintah seperti "makan makan", lalu mencari kecocokan nama setelah normalisasi huruf dan tanda baca. Bila tidak ada satu kecocokan pasti, chatbot menampilkan paling banyak lima nama mirip beserta penilaian masing-masing. Pencarian mendukung mi/mie dan typo ringan, tetapi tidak membuang kata pembeda seperti seafood. Kandidat tidak dianggap sebagai identitas pasti makanan pengguna. Pengguna dapat membalas dengan nama lengkap kandidat untuk mendapatkan penilaian khusus. Jawaban berasal dari penanda dataset, alasan kategori aplikasi, dan pantangan profil; alternatif berasal dari meal plan aktif. Data nutrisi yang kosong diberi penjelasan bahwa kosong bukan nol.

Penanda seafood, kacang, susu, telur, babi, alkohol, dan gorengan diteruskan dalam payload makanan. Filter pantangan meal plan juga menangani daging sapi. Pantangan bebas yang belum memiliki aturan terstruktur tetap membutuhkan pengembangan pemetaan; pemeriksaan ini bukan jaminan keamanan medis atau kelengkapan dataset.

## Penyampaian jawaban

LLM memilih variasi kalimat berbahasa Indonesia melalui indeks opsi yang disiapkan backend. Teks bebas hasil model tidak ditampilkan; nama makanan, angka, alasan, dan catatan data kosong tetap dipertahankan. Jika output model tidak valid atau layanan tidak tersedia, aplikasi memakai kalimat backend. Ini memberi variasi bahasa yang dibatasi, bukan parafrasa bebas yang bisa menambahkan klaim.

Makanan yang ditemukan tanpa pelanggaran dinyatakan dapat dipertimbangkan berdasarkan pemeriksaan yang tersedia; data nutrisi kosong tetap disebutkan. Pertanyaan boleh makan tidak lagi mengulang seluruh meal plan: alternatif dibatasi dua makanan pada slot yang relevan. Rekomendasi menu secara eksplisit tetap menampilkan menu aktif.

## Validasi

Tes mencakup rekomendasi menu tersimpan, nama makanan yang tidak tersedia, pantangan, preview tanpa penyimpanan, variasi sebagian menu, penolakan kandidat identik, pembatalan, konfirmasi kandidat persis, dan kandidat kedaluwarsa akibat perubahan profil/menu. Jalankan `pytest tests/chatbot tests/user -q` menggunakan konfigurasi path lokal pada Windows.
