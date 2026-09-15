# Buku Panduan PrediBeat

Panduan pengguna dan pengelola aplikasi

Versi dokumentasi 1.0 | 12 September 2026

PrediBeat membantu pengguna mengisi assessment, melihat target nutrisi dan rencana makan, mencatat konsumsi serta aktivitas, dan bertanya kepada chatbot Dr. Predia AI. Buku ini menjelaskan alur penggunaan aplikasi lokal dan langkah operasional untuk pengelola.

Mulailah dengan membuat akun dan melengkapi kuesioner. Setelah itu, gunakan dashboard untuk melihat target dan menu, lalu catat konsumsi yang benar-benar dilakukan di Progress Tracker. Chatbot dapat membantu membaca informasi dan menjalankan tindakan tertentu setelah dikonfirmasi.

## Isi panduan

1. Memulai dan melengkapi profil — halaman 2
2. Dashboard dan program makan — halaman 3
3. Mencatat progress harian — halaman 4
4. Bertanya kepada chatbot — halaman 5
5. Menjalankan tindakan melalui chatbot — halaman 6
6. Mengelola dataset dan dokumen — halaman 7
7. Menjalankan dan memperbarui aplikasi — halaman 8
8. Mengatasi kendala dan mencoba alur lengkap — halaman 9

## Ruang lingkup

Panduan ini mengikuti fitur pada kode proyek lokal saat dokumentasi dibuat. Contoh makanan bergantung pada isi dataset yang sedang aktif. Jawaban berbasis dokumen bergantung pada PDF yang sudah selesai diproses.

PrediBeat merupakan aplikasi pendamping pencatatan dan edukasi. Kategori risiko, Health Score, target, dan perkiraan perubahan berat badan merupakan keluaran aplikasi, bukan diagnosis atau hasil pengukuran medis.

<!-- pagebreak -->

# 1 Memulai dan melengkapi profil

## Membuka aplikasi

Pastikan pengelola sudah menjalankan layanan. Untuk konfigurasi Docker bawaan, buka http://localhost:8000 pada komputer yang menjalankan aplikasi. Jika WEB_PORT diubah, gunakan port tersebut. Pengguna perangkat lain perlu alamat server yang diberikan pengelola.

## Membuat akun

1. Buka halaman Sign Up atau alamat /register.
2. Isi username dengan 3 sampai 100 karakter, email yang valid, dan password minimal 8 karakter.
3. Kirim formulir pendaftaran. Username dan email harus belum digunakan akun lain.
4. Setelah berhasil, aplikasi mengarahkan pengguna ke kuesioner.

Untuk akun yang sudah ada, buka /login dan gunakan username atau email beserta password. Gunakan formulir akun biasa; ikon media sosial pada tampilan bukan alur masuk yang didokumentasikan di sini.

## Mengisi kuesioner

Isi bagian berikut sesuai keadaan pengguna dan perhatikan satuan setiap kolom.

- Profil Tubuh: usia, jenis kelamin, berat badan dalam kg, tinggi badan dalam cm, serta lingkar pinggang jika tersedia.
- Gaya Hidup Harian: konsumsi minuman manis, porsi nasi, olahraga, waktu duduk atau rebahan, tidur, riwayat keluarga, serta gejala yang ditanyakan.
- Pantangan, Penyakit, dan Lab: alergi atau pantangan, kondisi lain atau obat rutin, serta hasil gula darah puasa dan HbA1c jika tersedia. Jangan mengisi hasil lab dengan angka perkiraan.
- Pola Waktu dan Jadwal Makan: pola waktu makan, pilihan puasa bila digunakan, frekuensi makan, dan waktu makan yang diminta formulir.

Lanjutkan sampai seluruh bagian wajib terisi lalu kirim assessment. Jika muncul kesalahan validasi, perbaiki kolom yang ditandai dan kirim kembali. Hasil assessment dipakai untuk menyusun target dan meal plan.

## Memperbarui profil

Buka kembali /questionnaire ketika informasi profil berubah atau dashboard menampilkan pengingat pembaruan. Periksa data, ubah yang diperlukan, lalu kirim kembali. Setelah selesai, periksa ulang target dan menu di dashboard karena hasilnya dapat berubah mengikuti profil terbaru.

Gunakan Logout saat selesai menggunakan akun pada komputer bersama.

<!-- pagebreak -->

# 2 Dashboard dan program makan

## Membaca dashboard

Buka /dashboard setelah assessment selesai. Dashboard menampilkan ringkasan hasil, target kalori dan makronutrien, pola waktu makan, program diet aktif, serta Rencana Makan Hari Ini.

Perhatikan target karbohidrat, protein, dan lemak dalam gram. Menu yang ditampilkan adalah rencana; makanan tersebut belum otomatis berarti sudah dikonsumsi. Catat konsumsi sebenarnya melalui Progress Tracker.

## Memilih program diet

1. Buka Pilih Program atau halaman /diet.
2. Pilih program dan baca detailnya.
3. Untuk program yang tersedia, gunakan tombol Mulai Diet Ini. Program yang belum tersedia ditandai Coming Soon.
4. Kembali ke dashboard dan periksa nama diet aktif serta meal plan yang baru.

Program Low Carbohydrate dan Mediterranean dapat diaktifkan melalui tindakan chatbot. Pengaturan Intermittent Fasting tersedia melalui halaman aplikasi; perintah chatbot khusus untuk mengaktifkan atau mematikan IF belum tersedia.

## Membuat ulang menu

Gunakan tombol pembuatan ulang meal plan pada dashboard jika ingin mengganti menu aktif. Pembuatan ulang mengganti keseluruhan meal plan aktif, sehingga periksa menu baru sebelum mencatat konsumsi.

Pada detail diet, tombol Generate Ulang Diet Ini dapat muncul ketika program tersebut sudah aktif. Daftar makanan juga tersedia melalui halaman /menu.

## Menonaktifkan program

Gunakan Nonaktifkan pada dashboard atau Matikan Diet Aktif pada halaman detail. Penonaktifan diet membuat meal plan seimbang bawaan. Pengaturan pola waktu makan seperti IF memiliki tindakan tersendiri pada halaman terkait.

## Urutan penggunaan harian

1. Lihat target dan menu hari ini.
2. Periksa program diet dan pola makan yang aktif.
3. Setelah makan atau beraktivitas, buka Progress Tracker.
4. Catat makanan dan aktivitas yang benar-benar dilakukan.
5. Tinjau ringkasan progress; tanyakan penjelasannya kepada chatbot bila diperlukan.

<!-- pagebreak -->

# 3 Mencatat progress harian

## Menambahkan catatan

1. Buka /progress atau tombol Progress Tracker.
2. Pilih Tanggal catatan.
3. Pilih makanan dari meal plan yang benar-benar dikonsumsi dan sesuaikan jumlahnya.
4. Bila makanan tidak ada dalam meal plan, gunakan Tambahkan makanan lain. Cari namanya, pilih hasil yang sesuai, dan atur jumlah.
5. Pilih Aktivitas, Tipe atau Intensitas, dan Durasi menit jika ingin mencatat aktivitas.
6. Periksa pilihan lalu simpan formulir. Tinjau catatan tanggal tersebut untuk memastikan hasilnya sesuai.

Jumlah makanan mengikuti porsi dalam dataset. Dua porsi berarti dua kali porsi dasar makanan yang dipilih, bukan otomatis dua gram atau dua potong. Pastikan nama makanan dan ukuran porsinya sesuai sebelum menyimpan.

## Aturan tanggal

- Catatan dapat diisi untuk hari ini dan enam hari sebelumnya, yaitu rentang tujuh hari termasuk hari ini.
- Tanggal masa depan tidak dapat diisi.
- Catatan tanggal sebelumnya yang sudah tersimpan tidak dapat diedit atau dihapus melalui alur yang tersedia.
- Catatan hari ini dapat diperbarui. Jika menggunakan formulir lagi, periksa seluruh isi karena penyimpanan memperbarui catatan tanggal tersebut.

## Membaca ringkasan

Progress Tracker menampilkan informasi konsumsi, aktivitas, dan ringkasan mingguan. Nilai kalori masuk berasal dari makanan yang dipilih. Kalori aktivitas berasal dari jenis, intensitas, durasi, dan data profil yang digunakan aplikasi.

Health Score membantu membaca konsistensi data yang tercatat. Catatan yang belum lengkap dapat membuat ringkasan tidak mewakili kebiasaan sebenarnya. Perkiraan perubahan berat badan berasal dari perhitungan energi, bukan hasil penimbangan.

## Mencatat melalui chatbot

Perintah seperti “Tambahkan 2 porsi nasi putih ke tracker” menyiapkan kartu konfirmasi. Setelah dikonfirmasi, makanan ditambahkan ke catatan hari ini tanpa menghapus makanan yang sudah tercatat. Berbeda dengan pengisian formulir, tindakan ini menambah konsumsi pada catatan yang ada.

Jika makanan yang sama dicatat lagi melalui perintah baru, jumlah konsumsi dapat bertambah lagi. Periksa tracker sebelum mengulangi perintah yang sebelumnya sudah berhasil.

<!-- pagebreak -->

# 4 Bertanya kepada chatbot

## Cara menggunakan

Buka /chatbot atau Dr. Predia AI dari dashboard. Ketik satu pertanyaan yang jelas lalu tekan tombol kirim. Jawaban teks muncul bertahap ketika layanan AI mengirim respons. Tunggu respons selesai sebelum mengirim pertanyaan berikutnya.

## Kemampuan dan contoh pertanyaan

- Mengecek nutrisi makanan: “Berapa kalori nasi putih?” atau “Cek nutrisi telur rebus”. Data meliputi kalori, karbohidrat, protein, lemak, serat, gula, dan natrium sesuai dataset.
- Menghitung total beberapa makanan: “Saya makan 1 porsi nasi putih dan 2 porsi telur rebus, berapa total kalorinya?” Sebutkan jumlah atau gram secara jelas dan periksa porsi yang digunakan pada jawaban.
- Membandingkan makanan: “Bandingkan nasi putih dan nasi merah”. Perhatikan berat porsi masing-masing; perbandingan bawaan mengikuti porsi dataset dan belum tentu menggunakan berat yang sama.
- Mencari makanan dengan kriteria: “Cari makanan kalori maksimal 300 dan protein minimal 15”. Batas kalori menggunakan kkal, sedangkan protein menggunakan gram.
- Meminta rekomendasi dari dataset: “Rekomendasikan makanan tinggi serat” atau “Cari makanan gula maksimal 5”. Hasil bergantung pada makanan dan nilai yang tersedia.
- Menjelaskan profil dan progress: “Apa target kalori saya?”, “Apa diet aktif saya?”, atau “Jelaskan progress minggu ini”. Konteks mencakup profil, target, menu aktif, dan ringkasan minggu berjalan ketika tersedia.
- Menggunakan referensi PDF: “Berdasarkan dokumen, jelaskan manfaat serat untuk prediabetes”. Dokumen harus sudah diunggah dan selesai diproses oleh pengelola.

## Agar jawaban lebih tepat

Gunakan nama makanan lengkap, misalnya telur rebus alih-alih hanya telur. Jika ada beberapa pilihan, jawab dengan nama lengkap yang dimaksud. Untuk perhitungan, periksa bahwa chatbot menggunakan jumlah dan berat yang benar. Pertanyaan nutrisi saja tidak menyimpan makanan ke tracker.

Periksa label Sumber pada jawaban. Data makanan berasal dari dataset terstruktur, sedangkan penjelasan dokumen menggunakan referensi PDF yang tersedia. Label sumber tidak berarti seluruh kalimat AI pasti benar; cocokkan angka dengan data yang ditampilkan.

Riwayat percakapan bersifat terbatas dan disimpan sementara di memori server. Jangan mengandalkannya sebagai arsip permanen; keluar akun atau restart layanan dapat menghapus konteks percakapan.

<!-- pagebreak -->

# 5 Menjalankan tindakan melalui chatbot

## Perintah yang tersedia

- “Tambahkan 2 porsi nasi putih ke tracker” menyiapkan pencatatan makanan hari ini.
- “Catat nasi putih dan telur rebus” menyiapkan beberapa makanan sekaligus.
- “Ganti diet saya menjadi rendah karbo” mengganti program menjadi Low Carbohydrate dan membuat meal plan baru.
- “Ganti diet saya menjadi Mediterania” mengganti program menjadi Mediterranean dan membuat meal plan baru.
- “Nonaktifkan diet saya” menonaktifkan program diet dan membuat meal plan seimbang.
- “Buat ulang meal plan saya” mengganti seluruh menu aktif dengan hasil pembuatan ulang.

## Memeriksa dan mengonfirmasi tindakan

1. Kirim satu perintah tindakan.
2. Baca kartu konfirmasi dan dampak perubahan.
3. Untuk makanan, pilih kandidat yang benar dan sesuaikan jumlah dengan tombol tambah atau kurang. Jumlah per kelompok makanan dibatasi 1 sampai 20 porsi.
4. Klik tombol Konfirmasi untuk menjalankan pilihan pada kartu, atau Batal untuk membatalkan.
5. Tunggu pesan berhasil, lalu periksa Progress Tracker atau dashboard sesuai tindakannya.

Konfirmasi berlaku sekitar 10 menit. Jika kedaluwarsa atau server sudah restart, kirim ulang perintah agar kartu baru dibuat.

## Konfirmasi lewat teks

Jawaban singkat seperti “ya”, “oke”, atau “konfirmasi” dapat menjalankan tindakan terakhir yang masih menunggu. “Batal” atau “jangan” membatalkannya.

Konfirmasi teks memakai kandidat dan jumlah bawaan yang disimpan server. Jika sudah mengganti pilihan atau jumlah pada kartu, gunakan tombol Konfirmasi pada kartu agar perubahan pilihan tersebut ikut dikirim. Hindari membuat beberapa tindakan sekaligus sebelum menyelesaikan konfirmasi sebelumnya.

## Batas fitur chatbot saat ini

Chatbot menerima teks; tidak tersedia unggah foto makanan, pesan suara, atau unggah PDF langsung di panel chat. Chatbot tidak memiliki tindakan khusus untuk mengubah profil, mencatat aktivitas olahraga, menghapus catatan tracker, atau mengatur IF. Gunakan halaman aplikasi yang sesuai.

Jawaban bergantung pada data lokal dan layanan AI. Tidak tersedia penelusuran internet langsung untuk mencari berita atau referensi baru. Pembahasan di luar nutrisi dan penggunaan PrediBeat dapat diarahkan kembali ke cakupan aplikasi.

<!-- pagebreak -->

# 6 Mengelola dataset dan dokumen

Bagian ini ditujukan kepada pengelola instalasi lokal. Buka /admin untuk melihat pengelolaan dataset dan dokumen. Pada versi kode ini, portal admin belum menerapkan autentikasi admin pada rutenya; akses instalasi perlu dibatasi sebelum digunakan melalui jaringan publik.

## Mengganti dataset

1. Siapkan file CSV dengan struktur kolom yang sesuai dengan dataset aktif. Dataset referensi mencakup makanan, diet, dan aktivitas.
2. Pada Manajemen Dataset Referensi, pilih file pengganti untuk jenis dataset yang benar.
3. Gunakan tombol Ganti atau Upload pengganti sesuai halaman.
4. Periksa pesan hasil dan status dataset. Perbaiki file jika validasi menolaknya.
5. Jika tersedia atau diperlukan, jalankan reindex makanan dan tunggu proses selesai sebelum memeriksa hasil pencarian kembali.

Gunakan Pulihkan Backup untuk memilih dan memulihkan versi sebelumnya bila diperlukan. Pemulihan mengganti dataset aktif, sehingga pilih backup yang benar dan periksa hasilnya setelah selesai.

## Menambah referensi PDF

1. Pada Unggah Dokumen Baru, pilih atau seret file PDF ke area unggahan.
2. Klik Unggah Semua.
3. Pantau dokumen dan pekerjaan pemrosesan. Pending berarti menunggu; processing berarti sedang diproses; completed berarti selesai. Jika failed, periksa pesan kesalahan dan log worker.
4. Buka detail dokumen untuk memeriksa hasil pemrosesan yang tersedia.
5. Setelah selesai, uji dengan pertanyaan yang secara eksplisit merujuk isi dokumen melalui chatbot.

PDF tidak langsung menjadi sumber jawaban hanya karena sudah diunggah. Ekstraksi, pembuatan embedding, dan penyimpanan indeks harus selesai terlebih dahulu. Hasil pencarian juga bergantung pada relevansi isi dokumen dengan pertanyaan.

## Memeriksa mutu sumber

Pastikan dataset memiliki nama makanan, porsi, satuan, dan nilai nutrisi yang konsisten. Pilih PDF yang relevan dengan tujuan aplikasi dan pastikan teks hasil ekstraksi dapat dibaca. Gunakan contoh pertanyaan sederhana untuk memeriksa bahwa sumber yang diharapkan dapat ditemukan.

Penghapusan dokumen atau penggantian dataset mengubah sumber yang dapat digunakan aplikasi. Lakukan hanya pada data yang memang ingin dikelola, lalu periksa kembali hasil pencarian setelah perubahan.

<!-- pagebreak -->

# 7 Menjalankan dan memperbarui aplikasi

## Menjalankan instalasi yang sudah dikonfigurasi

Buka PowerShell pada folder proyek yang berisi docker-compose.yml dan file .env yang sudah diisi. Nyalakan Docker Desktop dan Ollama sesuai konfigurasi instalasi, lalu jalankan:

```powershell
docker compose up -d --build
docker compose ps
```

Buka http://localhost:8000 jika menggunakan port bawaan. Komponen Compose meliputi web, db, qdrant, dan rag-worker. Ollama harus dapat diakses melalui OLLAMA_BASE_URL; ia tidak otomatis dijalankan sebagai service Ollama oleh file Compose ini.

## Persiapan instalasi baru

Salin .env.example menjadi .env hanya jika file .env belum tersedia. Isi konfigurasi database, autentikasi, Ollama, dan Qdrant. Jangan menimpa konfigurasi instalasi yang sudah berjalan.

Model bawaan yang disebut proyek adalah llama3.1:8b untuk percakapan, bge-m3 untuk embedding, serta llava bila deskripsi gambar PDF digunakan. Pengelola perlu menyediakan model yang sesuai dengan konfigurasi aktif. Untuk menyiapkan model ekstraksi PDF MinerU, tersedia perintah:

```powershell
docker compose --profile setup run --rm mineru-models-download
```

## Setelah mengubah tampilan atau kode

Kode dan template dimasukkan ke image Docker. Setelah menyimpan perubahan, bangun ulang dan jalankan kembali service web dari folder proyek yang benar:

```powershell
docker compose up -d --build web
```

Kemudian muat ulang browser dengan Ctrl+F5. Jika perubahan menyentuh worker atau dependensinya, bangun ulang service terkait atau gunakan docker compose up -d --build untuk seluruh layanan.

## Memperbarui melalui GitHub

Gunakan folder clone yang memiliki .git, misalnya repo-update, untuk commit dan push. Menyalin kode ke folder clone atau melakukan push tidak otomatis memperbarui container yang berjalan dari folder lain. Sinkronkan kode ke folder yang dipakai menjalankan Compose, lalu bangun ulang di folder tersebut.

Simpan .env sebagai konfigurasi lokal. Jangan memasukkan secret, data runtime, atau backup pribadi ke commit. Pembaruan kode cukup dilakukan dengan build ulang; tidak perlu menghapus volume database.

<!-- pagebreak -->

# 8 Mengatasi kendala dan mencoba alur lengkap

## Kendala umum

- Halaman tidak terbuka: periksa Docker Desktop, hasil docker compose ps, port aplikasi, dan apakah perintah dijalankan dari folder proyek yang benar.
- Chatbot lambat pada pesan pertama: model lokal mungkin sedang dimuat. Coba satu pertanyaan singkat dan bandingkan respons berikutnya. Lama respons juga dipengaruhi perangkat, model, dan panjang pertanyaan.
- Layanan AI tidak dapat dihubungi: periksa Ollama, model yang tersedia, serta OLLAMA_BASE_URL. Jika memakai server melalui tunnel, pastikan tunnel aktif. Sebagian pertanyaan makanan dapat memperoleh jawaban terstruktur cadangan, tetapi kemampuan percakapan tidak penuh.
- Makanan tidak ditemukan: gunakan nama yang lebih spesifik atau pilih kandidat yang ditampilkan. Dataset dapat belum memiliki makanan tersebut.
- Referensi PDF tidak ditemukan: pastikan pemrosesan berstatus completed, isi dokumen relevan, dan layanan pencarian tersedia.
- Tindakan belum masuk tracker: pastikan sudah dikonfirmasi dan muncul pesan berhasil. Kartu kedaluwarsa perlu dibuat ulang.
- Catatan lama tidak bisa diedit: catatan hari sebelumnya yang sudah tersimpan memang dikunci oleh aplikasi.
- Tampilan masih lama: bangun ulang service web dari folder sumber yang benar, lalu Ctrl+F5.

Untuk diagnosis oleh pengelola, gunakan:

```powershell
docker compose logs --tail 100 web
docker compose logs --tail 100 rag-worker
ollama list
```

## Latihan penggunaan lengkap

1. Masuk dan lengkapi kuesioner.
2. Periksa target dan menu di dashboard.
3. Kirim “Cek nutrisi nasi putih” di chatbot; periksa nama dan porsi hasilnya.
4. Kirim “Bandingkan nasi putih dan nasi merah”.
5. Untuk latihan pencatatan, gunakan akun uji atau makanan yang memang ingin dicatat: kirim “Tambahkan 1 porsi nasi putih ke tracker”.
6. Periksa kartu, konfirmasi, lalu buka /progress dan pastikan catatan hari ini bertambah.
7. Kirim “Jelaskan progress minggu ini” dan cocokkan penjelasannya dengan catatan yang tersedia.

Untuk menguji perubahan diet tanpa mengubah data utama, gunakan akun uji. Perintah ganti diet dan buat ulang meal plan benar-benar mengganti menu setelah dikonfirmasi.

## Dasar dokumentasi

Fitur dipetakan dari README.md, docker-compose.yml, template halaman, route user_portal, progress_tracker dan chatbot, serta layanan chatbot_intent, chatbot_action, chatbot_tool, chatbot_context dan chatbot_orchestrator pada proyek lokal. Buku ini mendokumentasikan perilaku kode; hasil operasional bergantung pada konfigurasi dan data instalasi.
