# Sociovault

Sociovault adalah aplikasi web untuk mengelola data keluarga dan warga, program bantuan sosial, verifikasi kelayakan, serta pengajuan perubahan desil. Aplikasi menggunakan Flask, SQLAlchemy, Flask-Login, dan template Jinja.

## Persyaratan

- Python 3.10 atau lebih baru
- `pip`

Untuk penggunaan lokal, aplikasi memakai SQLite sehingga MySQL tidak perlu dipasang.

## Menyiapkan dan menjalankan aplikasi

Jalankan perintah berikut dari folder utama proyek di PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python seed.py
python run.py
```

Jika PowerShell menolak aktivasi virtual environment, jalankan perintah Python dan pip melalui path lengkap, misalnya:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe run.py
```

Buka <http://127.0.0.1:5000> setelah server berjalan. `seed.py` membuat tabel yang diperlukan dan mengisi data demo. Seeder dapat dijalankan kembali tanpa menghapus data yang sudah ada.

### Akun demo

| Peran | Username | Password |
|---|---|---|
| Administrator | `admin` | `admin123` |
| Petugas verifikasi | `petugas1` | `petugas123` |
| Warga | `warga_ratna` | `warga123` |
| Warga | `warga_bambang` | `warga123` |

Akun demo hanya untuk pengembangan lokal. Jangan gunakan kredensial ini pada deployment.

## Pengujian

Dengan virtual environment aktif:

```powershell
python -m unittest test_app.py
```

Atau jalankan tanpa aktivasi:

```powershell
.\.venv\Scripts\python.exe -m unittest test_app.py
```

## Konfigurasi

Salin `.env.example` menjadi `.env` untuk mengatur variabel lingkungan. Pengaturan bawaan menggunakan database `sociovault.db` di folder proyek dan server lokal di `127.0.0.1:5000`.

- `SECRET_KEY`: kunci sesi Flask; ganti dengan nilai acak sebelum deployment.
- `HOST`: alamat antarmuka server (default `127.0.0.1`).
- `PORT`: port server (default `5000`).
- `FLASK_DEBUG`: aktifkan mode debug untuk pengembangan, jangan aktifkan di production.
- `DATABASE_URL`: opsional. Tanpa nilai ini, aplikasi menggunakan SQLite. Untuk MySQL, isi dengan URL seperti `mysql+pymysql://user:password@127.0.0.1:3306/sociovault_db?charset=utf8mb4`.

## Struktur proyek

```text
app/                 Logika aplikasi dan blueprint Flask
  auth/              Login, registrasi, dan pengelolaan pengguna
  desil/             Informasi serta pengajuan perubahan desil
  program/           Pengelolaan program bantuan
  verifikasi/        Evaluasi kelayakan dan riwayat verifikasi
  warga/             Pengelolaan keluarga dan data warga
frontend/
  templates/         Template halaman Jinja
  static/            CSS, gambar, dan berkas unggahan
migrations/          Riwayat migrasi database
config.py            Konfigurasi aplikasi dan database
run.py               Entry point server
seed.py              Pembuatan tabel dan data demo
test_app.py          Pengujian aplikasi
requirements.txt     Dependensi Python
```

Jalankan perintah dari folder utama proyek. Folder `backend/` berisi salinan struktur lama; langkah pada panduan ini menggunakan entry point dan kode aplikasi di folder utama.
