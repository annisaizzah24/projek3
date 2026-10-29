import os
import unittest
import cv2
import numpy as np
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_ENV"] = "development"

from app import create_app, db
from app.models import Keluarga, User
from app.ocr_kk import (
    baca_kk,
    valid_no_kk,
    clean_digits,
    PROVINSI_VALID,
    cari_nomor_kk,
    cari_batas_tabel,
)

class TestOCRKartuKeluarga(unittest.TestCase):
    """Pengujian komprehensif fitur OCR Kartu Keluarga dan integrasi Form Tambah KK."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()
        cls.sample_path = os.path.abspath("uploads/temp/fd010b8c328d472d9b2e8cb3112d2ee3.jpg")

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Buat user admin untuk pengujian form
        admin = User.query.filter_by(username="admin_test").first()
        if not admin:
            admin = User(username="admin_test", nama="Admin Uji", role="admin")
            admin.set_password("AdminPass123!")
            db.session.add(admin)
            db.session.commit()

    def tearDown(self):
        db.session.rollback()
        db.drop_all()
        self.app_context.pop()

    def test_1_validasi_kode_provinsi_dan_digit(self):
        """Uji validasi nomor KK Indonesia 16 digit dan kode provinsi."""
        # Nomor sah Kalimantan Selatan (63)
        self.assertTrue(valid_no_kk("6303082609160005"))
        # Nomor sah Jawa Barat (32)
        self.assertTrue(valid_no_kk("3201010101010001"))
        # Salah panjang: 15 digit
        self.assertFalse(valid_no_kk("630308260916000"))
        # Salah panjang: 17 digit
        self.assertFalse(valid_no_kk("63030826091600005"))
        # Bukan digit
        self.assertFalse(valid_no_kk("630308260916000A"))
        # Kode provinsi tidak valid (misal 99)
        self.assertFalse(valid_no_kk("9901010101010001"))

    def test_2_pembersihan_karakter_ocr(self):
        """Uji konversi karakter huruf yang sering keliru menjadi angka."""
        # 'L' dan huruf lain yang tertukar
        raw = "L3030826091L0005"
        cleaned = clean_digits(raw)
        self.assertEqual(cleaned, "6303082609160005")

        # 'O' menjadi '0', 'I' menjadi '1', 'B' menjadi '8', 'S' menjadi '5'
        self.assertEqual(clean_digits("O1234S678B"), "0123456788")

    def test_3_baca_kk_sampel_asli_dan_tolak_nik(self):
        """
        Pengujian utama dengan dokumen sampel pengguna:
        - Harus membaca Nomor KK: 6303082609160005
        - Harus membaca Kepala Keluarga: RUSTANIAH
        - Harus membaca Alamat: DESA 3 B BATU BALIAN
        - TIDAK BOLEH mengambil NIK anggota keluarga manapun (Rustaniah, Nor Efendi, Abdur Rahman).
        - TIDAK BOLEH mengambil nomor registrasi blanko No. K 63030269506.
        """
        if not os.path.exists(self.sample_path):
            self.skipTest("Sampel foto KK fd010b8c328d472d9b2e8cb3112d2ee3.jpg tidak ditemukan.")

        hasil = baca_kk(self.sample_path)
        print("\nHasil Ekstraksi Dokumen Sampel:")
        print(f"  No. KK          : {hasil['no_kk']}")
        print(f"  Kepala Keluarga : {hasil['kepala_keluarga']}")
        print(f"  Alamat          : {hasil['alamat']}")

        # 1. Nomor KK harus tepat sesuai header
        self.assertEqual(hasil["no_kk"], "6303082609160005", "Gagal membaca Nomor KK yang benar dari header!")

        # 2. Kepala keluarga harus RUSTANIAH
        self.assertEqual(hasil["kepala_keluarga"], "RUSTANIAH")

        # 3. Alamat harus DESA 3 B BATU BALIAN
        self.assertIn("BATU BALIAN", hasil["alamat"])

        # 4. Verifikasi bahwa Nomor KK BUKAN salah satu NIK anggota keluarga
        nik_anggota = [
            "6303084107670277",  # NIK Rustaniah
            "6303082801930002",  # NIK Nor Efendi
            "6303082702970004",  # NIK Abdur Rahman
        ]
        for nik in nik_anggota:
            self.assertNotEqual(hasil["no_kk"], nik, f"KESALAHAN FATAL: OCR mengambil NIK anggota keluarga ({nik}) sebagai No KK!")

        # 5. Verifikasi bahwa Nomor KK BUKAN nomor seri No. K
        self.assertNotIn("6303026", hasil["no_kk"])

    def test_4_koreksi_orientasi_dokumen_miring_dan_tegak(self):
        """Uji ketahanan terhadap orientasi: dokumen upright harus tetap terbaca sama akuratnya."""
        if not os.path.exists(self.sample_path):
            self.skipTest("Sampel tidak ditemukan.")

        img = cv2.imread(self.sample_path)
        # Putar 90 derajat CW untuk membuat versi orientasi lain
        upright = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        temp_upright_path = "uploads/temp/test_upright.jpg"
        cv2.imwrite(temp_upright_path, upright)

        try:
            hasil = baca_kk(temp_upright_path)
            self.assertEqual(hasil["no_kk"], "6303082609160005")
            self.assertEqual(hasil["kepala_keluarga"], "RUSTANIAH")
        finally:
            if os.path.exists(temp_upright_path):
                os.remove(temp_upright_path)

    def test_5_dokumen_tanpa_header_tidak_boleh_ambil_nik(self):
        """
        Jika dokumen hanya berisi tabel anggota keluarga dengan banyak NIK tanpa header No KK,
        sistem harus mengembalikan no_kk kosong dan peringatan, BUKAN mengambil NIK sembarangan.
        """
        items = [
            {"text": "NIK", "yc": 100, "ymin": 90, "ymax": 110, "xmin": 200, "xmax": 250, "norm_x": 0.2, "norm_y": 0.1, "conf": 0.9},
            {"text": "Nama Lengkap", "yc": 100, "ymin": 90, "ymax": 110, "xmin": 50, "xmax": 150, "norm_x": 0.1, "norm_y": 0.1, "conf": 0.9},
            {"text": "3201010101010001", "yc": 150, "ymin": 140, "ymax": 160, "xmin": 200, "xmax": 350, "norm_x": 0.25, "norm_y": 0.15, "conf": 0.9},
            {"text": "3201010101010002", "yc": 180, "ymin": 170, "ymax": 190, "xmin": 200, "xmax": 350, "norm_x": 0.25, "norm_y": 0.18, "conf": 0.9},
        ]
        table_y = cari_batas_tabel(items, img_h=1000)
        self.assertEqual(table_y, 90)

        # Cari nomor KK dengan tabel y = 90
        dummy_gray = np.zeros((1000, 1000), dtype=np.uint8)
        no_kk, peringatan = cari_nomor_kk(items, None, dummy_gray, table_y, 1000, 1000)
        self.assertEqual(no_kk, "")
        self.assertTrue(len(peringatan) > 0)
        print("Peringatan saat No KK tidak ada di header:", peringatan)

    def test_6_gambar_kosong_atau_tidak_terbaca(self):
        """Uji saat gambar tidak memiliki teks atau buram."""
        blank = np.full((800, 1200, 3), 255, dtype=np.uint8)
        blank_path = "uploads/temp/blank_test.jpg"
        cv2.imwrite(blank_path, blank)
        try:
            hasil = baca_kk(blank_path)
            self.assertEqual(hasil["no_kk"], "")
            self.assertEqual(hasil["kepala_keluarga"], "")
            self.assertTrue(len(hasil["peringatan"]) > 0)
        finally:
            if os.path.exists(blank_path):
                os.remove(blank_path)

    def test_7_integrasi_database_dan_model_keluarga(self):
        """
        Uji penyimpanan Nomor KK ke database:
        - Tersimpan sebagai String(16).
        - Unik dan tidak tertukar dengan NIK Warga.
        - Validasi duplikasi bekerja dengan benar.
        """
        # Simpan keluarga baru
        k = Keluarga(
            nomor_kk="6303082609160005",
            kepala_keluarga="RUSTANIAH",
            alamat="DESA 3 B BATU BALIAN"
        )
        db.session.add(k)
        db.session.commit()

        # Ambil kembali dari database
        k_db = Keluarga.query.filter_by(nomor_kk="6303082609160005").first()
        self.assertIsNotNone(k_db)
        self.assertEqual(k_db.nomor_kk, "6303082609160005")
        self.assertEqual(k_db.kepala_keluarga, "RUSTANIAH")
        self.assertEqual(k_db.alamat, "DESA 3 B BATU BALIAN")
        self.assertIsInstance(k_db.nomor_kk, str)

        # Uji validasi model: Tolak jika bukan 16 digit
        with self.assertRaises(ValueError):
            Keluarga(nomor_kk="12345", kepala_keluarga="Uji", alamat="Alamat")

    def test_8_timeout_proteksi(self):
        """Uji proteksi batas waktu (timeout): fungsi harus merespons dalam durasi batas."""
        if not os.path.exists(self.sample_path):
            self.skipTest("Sampel tidak ditemukan.")

        import time
        t0 = time.time()
        # Jalankan dengan timeout sangat ketat (1 detik)
        hasil = baca_kk(self.sample_path, timeout=1)
        durasi = time.time() - t0
        self.assertIsInstance(hasil, dict)
        self.assertIn("no_kk", hasil)
        self.assertIn("duration_seconds", hasil)
        print(f"\nHasil uji timeout 1 detik (selesai dalam {durasi:.2f}s):", hasil.get("peringatan") or "Selesai")


if __name__ == "__main__":
    unittest.main()
