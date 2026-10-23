-- =============================================================================
-- Sociovault - Sistem Verifikasi Kelayakan Bantuan Sosial (Bansos)
-- Skema Database Relasional (MySQL 8.0+)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS sociovault_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE sociovault_db;

-- -----------------------------------------------------------------------------
-- 1. Tabel: users (Petugas & Administrator Sistem)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nama VARCHAR(100) NOT NULL,
    role ENUM('admin', 'petugas_verifikasi', 'warga') NOT NULL DEFAULT 'warga',
    nik VARCHAR(16) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 2. Tabel: keluarga (Data Kartu Keluarga)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS keluarga (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nomor_kk VARCHAR(16) NOT NULL UNIQUE,
    kepala_keluarga VARCHAR(100) NOT NULL,
    alamat TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_nomor_kk_format CHECK (CHAR_LENGTH(nomor_kk) = 16)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 3. Tabel: warga (Data Warga / Calon Penerima Bantuan)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warga (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_keluarga INT NOT NULL,
    nik VARCHAR(16) NOT NULL UNIQUE,
    nama VARCHAR(100) NOT NULL,
    alamat TEXT NOT NULL,
    penghasilan DECIMAL(15, 2) NOT NULL,
    jumlah_tanggungan INT NOT NULL DEFAULT 0,
    nilai_aset DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    tanggal_lahir DATE NOT NULL,
    desil INT NULL COMMENT 'Tingkat desil 1-10',
    foto_rumah VARCHAR(255) NULL COMMENT 'Path atau URL foto rumah tinggal',
    status_rumah VARCHAR(50) DEFAULT 'milik_sendiri' COMMENT 'Status kepemilikan rumah: milik_sendiri, sewa_kontrak, menumpang',
    luas_tanah INT DEFAULT 36 COMMENT 'Luas bangunan atau tanah rumah dalam m2',
    daya_listrik INT DEFAULT 450 COMMENT 'Daya listrik meteran PLN (VA)',
    jenis_kendaraan VARCHAR(50) DEFAULT 'tidak_ada' COMMENT 'Kepemilikan kendaraan bermotor',
    jumlah_kendaraan INT DEFAULT 0 COMMENT 'Jumlah unit kendaraan yang dimiliki',
    foto_kendaraan VARCHAR(255) NULL COMMENT 'Path foto bukti kepemilikan kendaraan',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_warga_keluarga FOREIGN KEY (id_keluarga) 
        REFERENCES keluarga (id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    CONSTRAINT chk_warga_nik_format CHECK (CHAR_LENGTH(nik) = 16),
    CONSTRAINT chk_warga_penghasilan CHECK (penghasilan >= 0),
    CONSTRAINT chk_warga_tanggungan CHECK (jumlah_tanggungan >= 0),
    CONSTRAINT chk_warga_aset CHECK (nilai_aset >= 0),
    CONSTRAINT chk_warga_desil CHECK (desil IS NULL OR (desil BETWEEN 1 AND 10))
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 4. Tabel: program_bantuan (Daftar Program Bantuan Sosial)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS program_bantuan (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_program VARCHAR(100) NOT NULL,
    kriteria_penghasilan_max DECIMAL(15, 2) NOT NULL,
    kriteria_tanggungan_min INT NOT NULL DEFAULT 0,
    kriteria_aset_max DECIMAL(15, 2) NULL,
    kriteria_desil_max INT NULL DEFAULT 4 COMMENT 'Batas maksimal desil yang berhak (default 4)',
    deskripsi TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_program_penghasilan CHECK (kriteria_penghasilan_max >= 0),
    CONSTRAINT chk_program_tanggungan CHECK (kriteria_tanggungan_min >= 0),
    CONSTRAINT chk_program_desil CHECK (kriteria_desil_max IS NULL OR (kriteria_desil_max BETWEEN 1 AND 10))
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 5. Tabel: verifikasi (Riwayat & Hasil Evaluasi Kelayakan Bansos)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verifikasi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_warga INT NOT NULL,
    id_program INT NOT NULL,
    id_petugas INT NOT NULL,
    status_otomatis ENUM('layak', 'tidak_layak', 'perlu_ditinjau') NOT NULL COMMENT 'hasil otomatis dari rule engine',
    status_final ENUM('layak', 'tidak_layak', 'perlu_ditinjau') NULL COMMENT 'hasil setelah konfirmasi petugas, NULL jika belum dikonfirmasi',
    catatan_petugas TEXT NULL,
    detail_pengecekan JSON NULL COMMENT 'simpan breakdown kriteria mana yang lolos/gagal, untuk audit',
    tanggal_verifikasi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tanggal_konfirmasi TIMESTAMP NULL,
    CONSTRAINT fk_verifikasi_warga FOREIGN KEY (id_warga) 
        REFERENCES warga (id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    CONSTRAINT fk_verifikasi_program FOREIGN KEY (id_program) 
        REFERENCES program_bantuan (id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    CONSTRAINT fk_verifikasi_petugas FOREIGN KEY (id_petugas) 
        REFERENCES users (id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    CONSTRAINT uq_warga_program UNIQUE (id_warga, id_program)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 6. Tabel: pengajuan_desil (Permohonan & Sanggah Perubahan Desil Warga)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pengajuan_desil (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_warga INT NOT NULL,
    id_user INT NOT NULL,
    desil_lama INT NOT NULL,
    desil_diajukan INT NOT NULL,
    penghasilan_terkini DECIMAL(15, 2) NOT NULL,
    jumlah_tanggungan INT DEFAULT 0,
    foto_rumah_baru VARCHAR(255) NOT NULL,
    dokumen_pendukung VARCHAR(255) NULL,
    alasan_pengajuan TEXT NOT NULL,
    status ENUM('menunggu', 'disetujui', 'ditolak') NOT NULL DEFAULT 'menunggu',
    catatan_petugas TEXT NULL,
    id_petugas INT NULL,
    tanggal_pengajuan TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tanggal_verifikasi TIMESTAMP NULL,
    CONSTRAINT fk_pengajuan_warga FOREIGN KEY (id_warga) 
        REFERENCES warga (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pengajuan_user FOREIGN KEY (id_user) 
        REFERENCES users (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pengajuan_petugas FOREIGN KEY (id_petugas) 
        REFERENCES users (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_desil_lama CHECK (desil_lama BETWEEN 1 AND 10),
    CONSTRAINT chk_desil_diajukan CHECK (desil_diajukan BETWEEN 1 AND 10)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- INDEXES TAMBAHAN UNTUK OPTIMASI PERFORMA QUERY
-- -----------------------------------------------------------------------------
CREATE INDEX idx_warga_nik ON warga(nik);
CREATE INDEX idx_warga_id_keluarga ON warga(id_keluarga);
CREATE INDEX idx_warga_desil ON warga(desil);
CREATE INDEX idx_pengajuan_desil_warga ON pengajuan_desil(id_warga);
CREATE INDEX idx_pengajuan_desil_status ON pengajuan_desil(status);
CREATE INDEX idx_verifikasi_id_warga ON verifikasi(id_warga);
CREATE INDEX idx_verifikasi_id_program ON verifikasi(id_program);
CREATE INDEX idx_verifikasi_tanggal ON verifikasi(tanggal_verifikasi);

-- -----------------------------------------------------------------------------
-- SEED DATA CONTOH UNTUK TESTING
-- Minimal: 1 admin, 1 petugas, 2 keluarga, 5 warga, 3 program bantuan
-- -----------------------------------------------------------------------------

-- 1. Users (Password: admin123, petugas123, warga123)
INSERT INTO users (id, username, password_hash, nama, role, nik) VALUES
(1, 'admin', 'scrypt:32768:8:1$YJc9V9QJ4qYjGk2N$60762a1a459388df6718cf226a35aee50b86a3d6ebefb6eeabf9b97b0a8863640b8a1c8751515ef58055eeadcbdaafcf4b647f0e9b626e5be79fc5fcd0d9bfad', 'Administrator Pusat', 'admin', NULL),
(2, 'petugas1', 'scrypt:32768:8:1$cK69K2vA9m1bLxQz$98188e7b15a6b7ef99ca7da61bb8d99d1469e38fecbb8eb2a543329f60f64cbbfe7b51b329433604f14dbe15f212239d5e3ae101b0f5905d41f7e0fc6cf938a4', 'Rudi Hartono (Petugas Lapangan)', 'petugas_verifikasi', NULL),
(3, 'warga_ratna', 'scrypt:32768:8:1$C3iE72UQQwSw2uB8$7e6d4a3aee8b57637f77eef31ea2692227b346ab0aef3d28ef6d4abc10c625dcd77c36cd598f1651693ddee1aa8ebbb217407e2daab62bb708696836bc70bab9', 'Ratna Sari', 'warga', '3201010505910005'),
(4, 'warga_bambang', 'scrypt:32768:8:1$B6HAEJnc4xSOWTin$ea90c52ba3d6f661c9687a34cddfca6ae48d20282dc5af8c9817aa085b70172f82373e26a0f5200ed221e3aa3be69a13fd7cadd794a52bf35e05c5acdad37fde', 'Bambang Sudarmono', 'warga', '3201010101900001')
ON DUPLICATE KEY UPDATE username=username;

-- 2. Keluarga (Minimal 2 Keluarga)
INSERT INTO keluarga (id, nomor_kk, kepala_keluarga, alamat) VALUES
(1, '3201012345670001', 'Bambang Sudarmono', 'Jl. Sukajadi No. 45 RT 01/RW 03, Bandung'),
(2, '3201012345670002', 'Slamet Riyadi', 'Jl. Cibaduyut Raya No. 12 RT 04/RW 02, Bandung')
ON DUPLICATE KEY UPDATE nomor_kk=nomor_kk;

-- 3. Warga (Lengkap dengan desil, foto rumah, dan parameter aset fisik)
INSERT INTO warga (
    id, id_keluarga, nik, nama, alamat, penghasilan, jumlah_tanggungan, nilai_aset, 
    tanggal_lahir, desil, foto_rumah, status_rumah, luas_tanah, daya_listrik, 
    jenis_kendaraan, jumlah_kendaraan, foto_kendaraan
) VALUES
(1, 1, '3201010101900001', 'Bambang Sudarmono', 'Jl. Sukajadi No. 45 RT 01/RW 03, Bandung', 1200000.00, 3, 6000000.00, '1990-01-01', 2, 'images/rumah/rumah_desil2_sederhana.svg', 'sewa_kontrak', 30, 450, 'motor', 1, 'images/rumah/motor_sample.svg'),
(2, 1, '3201010202920002', 'Siti Maryam', 'Jl. Sukajadi No. 45 RT 01/RW 03, Bandung', 0.00, 3, 0.00, '1992-02-02', 1, 'images/rumah/rumah_desil1_bilik.svg', 'menumpang', 20, 450, 'tidak_ada', 0, NULL),
(3, 1, '3201010303150003', 'Dimas Anggara', 'Jl. Sukajadi No. 45 RT 01/RW 03, Bandung', 0.00, 0, 0.00, '2015-03-03', 1, 'images/rumah/rumah_desil1_bilik.svg', 'menumpang', 20, 450, 'tidak_ada', 0, NULL),
(4, 2, '3201010404880004', 'Slamet Riyadi', 'Jl. Cibaduyut Raya No. 12 RT 04/RW 02, Bandung', 4800000.00, 1, 135000000.00, '1988-04-04', 7, 'images/rumah/rumah_desil7_permanen.svg', 'milik_sendiri', 90, 2200, 'mobil', 1, NULL),
(5, 2, '3201010505910005', 'Ratna Sari', 'Jl. Cibaduyut Raya No. 12 RT 04/RW 02, Bandung', 850000.00, 2, 0.00, '1991-05-05', 7, 'images/rumah/rumah_desil7_permanen.svg', 'sewa_kontrak', 24, 450, 'tidak_ada', 0, NULL)
ON DUPLICATE KEY UPDATE 
    penghasilan=VALUES(penghasilan),
    nilai_aset=VALUES(nilai_aset),
    desil=VALUES(desil),
    foto_rumah=VALUES(foto_rumah),
    status_rumah=VALUES(status_rumah),
    luas_tanah=VALUES(luas_tanah),
    daya_listrik=VALUES(daya_listrik),
    jenis_kendaraan=VALUES(jenis_kendaraan),
    jumlah_kendaraan=VALUES(jumlah_kendaraan),
    foto_kendaraan=VALUES(foto_kendaraan);

-- 4. Program Bantuan (Minimal 3 Program dengan kriteria aset & status aktif)
INSERT INTO program_bantuan (id, nama_program, kriteria_penghasilan_max, kriteria_tanggungan_min, kriteria_aset_max, deskripsi, is_active) VALUES
(1, 'Program Keluarga Harapan (PKH)', 2000000.00, 2, 15000000.00, 'Bantuan sosial bersyarat bagi keluarga rentan miskin dengan tanggungan anak sekolah atau balita.', TRUE),
(2, 'Bantuan Pangan Non-Tunai (BPNT)', 2500000.00, 0, 25000000.00, 'Bantuan pemenuhan pangan sembako pokok setiap bulan bagi warga prasejahtera.', TRUE),
(3, 'Bantuan Langsung Tunai (BLT) Kemiskinan Ekstrem', 1500000.00, 1, 10000000.00, 'Bantuan uang tunai langsung bagi masyarakat rentan dengan tingkat ekonomi paling rendah.', TRUE)
ON DUPLICATE KEY UPDATE nama_program=nama_program;

-- 5. Contoh Data Verifikasi Awal
INSERT INTO verifikasi (id, id_warga, id_program, id_petugas, status_otomatis, status_final, catatan_petugas, detail_pengecekan, tanggal_verifikasi, tanggal_konfirmasi) VALUES
(1, 1, 1, 2, 'layak', 'layak', 'Telah disurvei kondisi rumah sesuai kriteria prasejahtera.', 
 '{"penghasilan": {"nilai": 1200000.0, "batas_max": 2000000.0, "lolos": true}, "tanggungan": {"nilai": 3, "batas_min": 2, "lolos": true}, "aset": {"nilai": 5000000.0, "batas_max": 15000000.0, "lolos": true}, "data_lengkap": true, "ringkasan": "Semua kriteria terpenuhi."}', 
 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(2, 4, 1, 2, 'tidak_layak', 'tidak_layak', 'Penghasilan dan aset melebihi ketentuan program.', 
 '{"penghasilan": {"nilai": 4800000.0, "batas_max": 2000000.0, "lolos": false}, "tanggungan": {"nilai": 1, "batas_min": 2, "lolos": false}, "aset": {"nilai": 35000000.0, "batas_max": 15000000.0, "lolos": false}, "data_lengkap": true, "ringkasan": "Penghasilan dan aset melebihi batas."}', 
 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON DUPLICATE KEY UPDATE id=id;
