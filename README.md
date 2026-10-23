# Sociovault - Sistem Verifikasi Kelayakan Bantuan Sosial (Bansos)

Sociovault adalah sistem evaluasi bantuan sosial fullstack berbasis **Flask (Python)**, **SQLAlchemy**, dan antarmuka **Jinja2 + Bootstrap 5**. Sistem ini dirancang untuk mengelola data kependudukan (Keluarga & Warga), master kriteria program bansos, serta evaluasi otomatis kelayakan berbasis aturan (**Rule Engine**) dengan audit log dan konfirmasi petugas.

---

## 📁 Struktur Arsitektur: Pemisahan Backend & Frontend

Proyek ini telah ditata secara terpisah dan rapi agar memudahkan identifikasi antara modul pemrosesan logika server (**Backend**) dan modul antarmuka pengguna (**Frontend**):

```
projek3/ (sociovault/)
│
├── 🧠 backend/                      # LAYER 1: BACKEND (Server Logic, Database, & API)
│   ├── app/
│   │   ├── __init__.py              # Factory Flask & registrasi Blueprint
│   │   ├── extensions.py            # Instance SQLAlchemy, LoginManager, Migrate
│   │   ├── forms.py                 # Validasi form Flask-WTF & custom validators
│   │   ├── models.py                # Definisi ORM Model SQLAlchemy & @validates
│   │   ├── auth/                    # Modul Autentikasi & Role-Based Access Control
│   │   │   ├── __init__.py
│   │   │   └── routes.py            # Login, logout, registrasi petugas (@role_required)
│   │   ├── warga/                   # Modul Manajemen Data Kependudukan
│   │   │   ├── __init__.py
│   │   │   └── routes.py            # CRUD Warga, KK, filter pencarian
│   │   ├── program/                 # Modul Master Program Bantuan Sosial
│   │   │   ├── __init__.py
│   │   │   └── routes.py            # CRUD Kriteria Program Bansos (Admin only)
│   │   └── verifikasi/              # Modul Inti Evaluasi & Verifikasi Bansos
│   │       ├── __init__.py
│   │       ├── engine.py            # RULE ENGINE: jalankan_verifikasi() & logging audit
│   │       └── routes.py            # Form eksekusi evaluasi & form konfirmasi petugas
│   ├── logs/
│   │   └── verifikasi_audit.log     # File log rekaman audit evaluasi verifikasi
│   ├── config.py                    # Konfigurasi aplikasi & koneksi database
│   ├── schema.sql                   # Skrip DDL MySQL relasional lengkap & data seed
│   ├── models.py                    # Re-export model SQLAlchemy (Deliverable Bagian 1)
│   ├── seed.py                      # Skrip seeder data awal testing
│   ├── sociovault.db                # Database SQLite lokal
│   ├── test_app.py                  # 10 Skenario pengujian Unit Test lengkap
│   └── run.py                       # Server runner lokal direktori backend
│
├── 🎨 frontend/                     # LAYER 2: FRONTEND (UI, Templates, & Assets)
│   ├── templates/                   # Berkas Template Jinja2 (HTML View)
│   │   ├── base.html                # Master layout dengan Responsive Sidebar Nav
│   │   ├── dashboard.html           # Dashboard statistik ringkasan & Chart.js doughnut
│   │   ├── macros.html              # Komponen reusable: status badge & render_field
│   │   ├── auth/                    # Halaman Autentikasi & Akun
│   │   │   ├── login.html           # Form login pengguna
│   │   │   ├── petugas.html         # Daftar akun petugas & administrator
│   │   │   └── form_petugas.html    # Form tambah akun petugas/admin
│   │   ├── warga/                   # Halaman Data Warga & Kartu Keluarga
│   │   │   ├── index.html           # Tabel data warga, pencarian, & filter KK
│   │   │   ├── form_warga.html      # Form pendaftaran & edit warga (WTForms inline)
│   │   │   └── form_keluarga.html   # Form tambah KK baru
│   │   ├── program/                 # Halaman Master Program Bantuan
│   │   │   ├── index.html           # Tabel daftar program bansos & toggle status
│   │   │   └── form_program.html    # Form tambah & edit program bansos (Admin)
│   │   ├── verifikasi/              # Halaman Proses & Audit Verifikasi
│   │   │   ├── form_verifikasi.html # Form pemilihan warga & program bansos
│   │   │   ├── detail.html          # Breakdown audit kriteria & form konfirmasi
│   │   │   └── index.html           # Tabel riwayat verifikasi & filter multi-parameter
│   │   └── errors/                  # Halaman Penanganan Error Kustom
│   │       ├── 403.html             # Halaman 403 Akses Ditolak (RBAC)
│   │       └── 404.html             # Halaman 404 Tidak Ditemukan
│   └── static/                      # Aset Client-side Statis
│       └── css/
│           ├── style.css            # Styling struktur dasar layout
│           └── custom.css           # Styling status badge & validasi invalid-feedback
│
├── 🚀 Root Launchers & Helpers      # Penghubung / Runner Level Root
│   ├── run.py                       # Entry point utama untuk menjalankan aplikasi
│   ├── seed.py                      # Seeder runner level root
│   ├── test_app.py                  # Test runner level root (10 unit test)
│   ├── schema.sql                   # Berkas DDL database relasional
│   ├── models.py                    # Re-export model ORM
│   ├── requirements.txt             # Dependensi Python
│   ├── .env.example                 # Contoh konfigurasi environment
│   └── .gitignore                   # Konfigurasi pengabaian Git
```

---

## 🔍 Perbedaan Tanggung Jawab: Backend vs Frontend

| Komponen | **Backend (`backend/`)** | **Frontend (`frontend/`)** |
| :--- | :--- | :--- |
| **Bahasa / Format** | Python 3.10+, SQL | Jinja2 HTML5, CSS3, JavaScript (Chart.js via CDN) |
| **Fokus Utama** | Logika bisnis, pemrosesan data, validasi server, keamanan, & database | Antarmuka pengguna (UI/UX), tata letak, formulir input, responsifitas |
| **Fitur Utama** | • ORM SQLAlchemy & skema relasional<br>• Rule Engine (`jalankan_verifikasi`)<br>• Audit logger ke `logs/verifikasi_audit.log`<br>• Autentikasi session & `@role_required`<br>• 10 Skenario pengujian unit test | • Navigasi Sidebar Responsif (Bootstrap 5)<br>• Macro inline error per-field (`render_field`)<br>• Status badge dinamis (Hijau, Merah, Kuning)<br>• Chart.js grafik status bansos<br>• Halaman kustom 403 & 404 |
| **Validasi** | Memastikan integritas data NIK 16 digit, foreign key cascade, pencegahan pendaftaran ganda | Menampilkan highlight merah (`is-invalid`) dan pesan kesalahan tepat di bawah input |

---

## ⚙️ Cara Menjalankan Aplikasi

### 1. Menjalankan Server Aplikasi
Jalankan perintah ini dari folder root proyek:
```powershell
& "C:\Users\asus\OneDrive\Documents\Bansos warga\.venv\Scripts\python.exe" run.py
```
Aplikasi akan aktif di **`http://127.0.0.1:5000`**.

### 2. Akun Demo Bawaan
* **Administrator**: `admin` / `admin123` *(Hak akses penuh: master program, warga, verifikasi, kelola petugas)*
* **Petugas Verifikasi**: `petugas1` / `petugas123` *(Hak akses: data warga & pengesahan verifikasi bansos)*

### 3. Menjalankan Unit Tests (10 Skenario)
```powershell
& "C:\Users\asus\OneDrive\Documents\Bansos warga\.venv\Scripts\python.exe" -m unittest test_app.py
```

### 4. Mengisi Ulang Data Dummy (Seeder)
```powershell
& "C:\Users\asus\OneDrive\Documents\Bansos warga\.venv\Scripts\python.exe" seed.py
```
