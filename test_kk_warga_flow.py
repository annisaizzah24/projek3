import os
import io
import json
import unittest
from PIL import Image

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_ENV"] = "development"

from app import create_app, db
from app.models import User, Keluarga


class TestKKWargaFlow(unittest.TestCase):
    """Pengujian terintegrasi pemindahan fitur Unggah KK + OCR ke Akun Warga & Verifikasi Admin."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.sample_jpg = os.path.abspath("uploads/temp/fd010b8c328d472d9b2e8cb3112d2ee3.jpg")

    def setUp(self):
        self.client = self.app.test_client()
        self.created_files = []
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()

            admin = User(username="admin_uji", nama="Admin Uji", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)

            warga_a = User(username="warga_a", nama="Warga A", role="warga", nik="6303084107670277")
            warga_a.set_password("warga123")
            db.session.add(warga_a)

            warga_b = User(username="warga_b", nama="Warga B", role="warga", nik="3201010101900099")
            warga_b.set_password("warga123")
            db.session.add(warga_b)

            db.session.commit()
            self.admin_id = admin.id
            self.warga_a_id = warga_a.id
            self.warga_b_id = warga_b.id

    def tearDown(self):
        for rel in self.created_files:
            abs_p = os.path.abspath(rel)
            if os.path.exists(abs_p):
                os.remove(abs_p)
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self, username, password):
        return self.client.post("/auth/login", data={"username": username, "password": password}, follow_redirects=True)

    def _logout(self):
        return self.client.get("/auth/logout", follow_redirects=True)

    def test_1_2_tampilan_admin_dan_warga(self):
        """
        Uji #1 & #2:
        - Tombol + Kartu Keluarga tidak ada di Admin -> Data Warga.
        - Tombol + Tambah Warga tetap ada.
        - Bagian 'Dokumen Kartu Keluarga' tersedia di halaman Akun Warga (/dashboard).
        """
        self._login("admin_uji", "admin123")
        res_admin = self.client.get("/warga")
        html_admin = res_admin.get_data(as_text=True)
        self.assertEqual(res_admin.status_code, 200)
        self.assertNotIn("+ Kartu Keluarga", html_admin)
        self.assertIn("+ Tambah Warga", html_admin)
        self.assertIn("Verifikasi Dokumen Kartu Keluarga", html_admin)
        self._logout()

        self._login("warga_a", "warga123")
        res_warga = self.client.get("/dashboard")
        html_warga = res_warga.get_data(as_text=True)
        self.assertEqual(res_warga.status_code, 200)
        self.assertIn("Dokumen Kartu Keluarga", html_warga)
        self.assertIn("Proses OCR", html_warga)
        self.assertIn("Simpan Data", html_warga)
        self.assertIn("Belum Diunggah", html_warga)

    def test_3_4_5_6_ocr_jpg_png_pdf_dan_no_kk_bukan_nik(self):
        """
        Uji #3, #4, #5, #6:
        - Upload JPG, PNG, dan PDF ke endpoint OCR (/akun/kk/ocr).
        - OCR berjalan nyata dan membaca No. KK (6303082609160005), BUKAN NIK anggota keluarga.
        - Mengenali metadata wilayah & daftar anggota keluarga.
        """
        if not os.path.exists(self.sample_jpg):
            self.skipTest("Sampel foto KK tidak ditemukan.")

        self._login("warga_a", "warga123")

        img = Image.open(self.sample_jpg).convert("RGB")

        # Uji JPG
        with open(self.sample_jpg, "rb") as f:
            res_jpg = self.client.post(
                "/akun/kk/ocr",
                data={"dokumen_kk": (f, "kk_test.jpg")},
                content_type="multipart/form-data"
            )
        self.assertEqual(res_jpg.status_code, 200)
        data_jpg = res_jpg.get_json()
        self.assertEqual(data_jpg["no_kk"], "6303082609160005")
        self.assertNotIn(data_jpg["no_kk"], ["6303084107670277", "6303082805930002", "6303082702970004"])
        self.assertEqual(data_jpg["kepala_keluarga"], "RUSTANIAH")
        self.assertIn("BATU BALIAN", data_jpg["alamat"])
        self.assertTrue(len(data_jpg.get("anggota_keluarga", [])) >= 1)

        # Uji PNG
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_buf.seek(0)
        res_png = self.client.post(
            "/akun/kk/ocr",
            data={"dokumen_kk": (png_buf, "kk_test.png")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res_png.status_code, 200)
        data_png = res_png.get_json()
        self.assertEqual(data_png["no_kk"], "6303082609160005")

        # Uji PDF
        pdf_buf = io.BytesIO()
        img.save(pdf_buf, format="PDF")
        pdf_buf.seek(0)
        res_pdf = self.client.post(
            "/akun/kk/ocr",
            data={"dokumen_kk": (pdf_buf, "kk_test.pdf")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res_pdf.status_code, 200)
        data_pdf = res_pdf.get_json()
        self.assertEqual(data_pdf["no_kk"], "6303082609160005")
        self.assertEqual(data_pdf["provinsi"], "KALIMANTAN SELATAN")

    def test_7_8_9_10_11_simpan_admin_verifikasi_riwayat_dan_keamanan(self):
        """
        Uji #7, #8, #9, #10, #11:
        - Edit hasil OCR lalu simpan ke database oleh Warga A.
        - Dokumen muncul di halaman Admin (/warga).
        - Admin melakukan verifikasi (Perlu Perbaikan -> Warga A upload ulang -> Terverifikasi)
          dan riwayat verifikasi sebelumnya tidak hilang.
        - Warga B dilarang mengakses dokumen Warga A (403 Forbidden) dan dilarang menduplikasi No. KK.
        """
        self._login("warga_a", "warga123")

        # Buat gambar PNG valid kecil sebagai dokumen upload
        img_buf = io.BytesIO()
        Image.new("RGB", (200, 120), color=(255, 255, 255)).save(img_buf, format="PNG")
        img_buf.seek(0)

        ocr_snapshot = json.dumps({
            "anggota_keluarga": [{"no": 1, "nama": "RUSTANIAH", "nik": "6303084107670277"}],
            "raw": "KARTU KELUARGA No. 6303082609160005"
        })

        # Simpan dengan data yang diedit oleh warga
        res_save = self.client.post(
            "/akun/kk/simpan",
            data={
                "nomor_kk": "6303082609160005",
                "kepala_keluarga": "RUSTANIAH (Edited)",
                "alamat": "DESA BATU BALIAN NO 3B",
                "rt_rw": "003/001",
                "desa_kelurahan": "BATU BALIAN",
                "kecamatan": "SIMPANG EMPAT",
                "kabupaten_kota": "BANJAR",
                "provinsi": "KALIMANTAN SELATAN",
                "hasil_ocr_json": ocr_snapshot,
                "dokumen_kk": (img_buf, "kk_a.png")
            },
            content_type="multipart/form-data"
        )
        self.assertEqual(res_save.status_code, 200)
        save_json = res_save.get_json()
        self.assertTrue(save_json["success"])
        self.assertEqual(save_json["status_dokumen"], "Menunggu Verifikasi")
        kk_id = save_json["keluarga_id"]

        with self.app.app_context():
            kk = db.session.get(Keluarga, kk_id)
            self.assertIsNotNone(kk)
            self.assertEqual(kk.id_user, self.warga_a_id)
            self.assertEqual(kk.kepala_keluarga, "RUSTANIAH (Edited)")
            self.assertEqual(kk.rt_rw, "003/001")
            self.assertIsNotNone(kk.dokumen_kk)
            self.created_files.append(kk.dokumen_kk)

        # Warga A boleh lihat dokumen miliknya
        res_view_a = self.client.get(f"/keluarga/dokumen/{kk_id}")
        self.assertEqual(res_view_a.status_code, 200)
        res_view_a.close()
        self._logout()

        # Uji #11: Warga B tidak boleh mengakses dokumen Warga A (403) & tidak boleh menduplikasi No. KK
        self._login("warga_b", "warga123")
        res_view_b = self.client.get(f"/keluarga/dokumen/{kk_id}")
        self.assertEqual(res_view_b.status_code, 403)

        pdf_buf = io.BytesIO()
        Image.new("RGB", (200, 120), color=(240, 240, 240)).save(pdf_buf, format="PDF")
        pdf_buf.seek(0)
        res_dup = self.client.post(
            "/akun/kk/simpan",
            data={
                "nomor_kk": "6303082609160005",
                "kepala_keluarga": "Palsu",
                "alamat": "Alamat lain",
                "dokumen_kk": (pdf_buf, "kk_b.pdf")
            },
            content_type="multipart/form-data"
        )
        self.assertEqual(res_dup.status_code, 400)
        self.assertFalse(res_dup.get_json()["success"])
        self._logout()

        # Uji #9 & #10: Admin melihat dokumen di /warga dan memverifikasi
        self._login("admin_uji", "admin123")
        res_admin_list = self.client.get("/warga")
        html_admin = res_admin_list.get_data(as_text=True)
        self.assertIn("6303082609160005", html_admin)
        self.assertIn("RUSTANIAH (Edited)", html_admin)

        res_admin_doc = self.client.get(f"/keluarga/dokumen/{kk_id}")
        self.assertEqual(res_admin_doc.status_code, 200)
        res_admin_doc.close()

        # Admin tandai Perlu Perbaikan
        res_revisi = self.client.post(
            f"/keluarga/{kk_id}/verifikasi-dokumen",
            data={"aksi": "perlu_perbaikan", "catatan_verifikasi": "Mohon foto ulang lebih terang"},
            follow_redirects=True
        )
        self.assertEqual(res_revisi.status_code, 200)
        with self.app.app_context():
            kk = db.session.get(Keluarga, kk_id)
            self.assertEqual(kk.status_dokumen, "Perlu Perbaikan")
            self.assertEqual(kk.catatan_verifikasi, "Mohon foto ulang lebih terang")
        self._logout()

        # Warga A mengunggah dokumen baru (PDF) -> riwayat verifikasi sebelumnya tetap terjaga!
        self._login("warga_a", "warga123")
        pdf_buf2 = io.BytesIO()
        Image.new("RGB", (200, 120), color=(255, 255, 255)).save(pdf_buf2, format="PDF")
        pdf_buf2.seek(0)
        res_reupload = self.client.post(
            "/akun/kk/simpan",
            data={
                "nomor_kk": "6303082609160005",
                "kepala_keluarga": "RUSTANIAH",
                "alamat": "DESA BATU BALIAN NO 3B",
                "dokumen_kk": (pdf_buf2, "kk_a_baru.pdf")
            },
            content_type="multipart/form-data"
        )
        self.assertEqual(res_reupload.status_code, 200)
        with self.app.app_context():
            kk = db.session.get(Keluarga, kk_id)
            self.created_files.append(kk.dokumen_kk)
            self.assertEqual(kk.status_dokumen, "Menunggu Verifikasi")
            self.assertTrue(kk.dokumen_kk.endswith(".pdf"))
            self.assertTrue(len(kk.riwayat_dokumen) >= 3)
            # Pastikan catatan verifikasi sebelumnya terarsip di riwayat
            archived_notes = [r.get("catatan") or r.get("catatan_sebelumnya") for r in kk.riwayat_dokumen]
            self.assertIn("Mohon foto ulang lebih terang", archived_notes)
        self._logout()

        # Admin menyetujui (Terverifikasi)
        self._login("admin_uji", "admin123")
        res_ok = self.client.post(
            f"/keluarga/{kk_id}/verifikasi-dokumen",
            data={"aksi": "terverifikasi", "catatan_verifikasi": "Dokumen sesuai dan sah"},
            follow_redirects=True
        )
        self.assertEqual(res_ok.status_code, 200)
        with self.app.app_context():
            kk = db.session.get(Keluarga, kk_id)
            self.assertEqual(kk.status_dokumen, "Terverifikasi")


if __name__ == "__main__":
    unittest.main()
