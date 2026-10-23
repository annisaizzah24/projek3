import os
import io
import unittest
import datetime
from decimal import Decimal

# Set in-memory database URL before importing create_app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_ENV"] = "development"

from app import create_app, db
from app.models import User, Keluarga, Warga, ProgramBantuan, Verifikasi, PengajuanDesil, DESIL_INFO, get_desil_info
from app.verifikasi.engine import jalankan_verifikasi, AlreadyVerifiedError, NotFoundError


class SociovaultTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()

            # 1. Seed admin & petugas
            admin = User(username="admin", nama="Admin Test", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)

            petugas = User(username="petugas1", nama="Petugas Test", role="petugas_verifikasi")
            petugas.set_password("petugas123")
            db.session.add(petugas)

            # 2. Seed 1 keluarga
            keluarga = Keluarga(
                nomor_kk="3201012345670001",
                kepala_keluarga="Bambang Test",
                alamat="Jl. Uji Coba No. 1"
            )
            db.session.add(keluarga)
            db.session.commit()

            # 3. Seed 1 program bantuan aktif dengan batas aset
            program = ProgramBantuan(
                nama_program="PKH Test",
                kriteria_penghasilan_max=Decimal("2000000.00"),
                kriteria_tanggungan_min=2,
                kriteria_aset_max=Decimal("15000000.00"),
                deskripsi="Program uji coba",
                is_active=True
            )
            db.session.add(program)
            db.session.commit()

            # 4. Seed 1 warga layak (penghasilan <= 2jt, tanggungan >= 2, aset <= 15jt)
            warga_layak = Warga(
                nik="3201010101900001",
                nama="Budi Layak",
                alamat="Jl. Sukajadi No. 10",
                id_keluarga=keluarga.id,
                penghasilan=Decimal("1200000.00"),
                jumlah_tanggungan=3,
                nilai_aset=Decimal("5000000.00"),
                tanggal_lahir=datetime.date(1990, 1, 1)
            )
            db.session.add(warga_layak)

            # 5. Seed 1 warga tidak layak (penghasilan 5jt > 2jt)
            warga_tidak_layak = Warga(
                nik="3201010202850002",
                nama="Siti Mampu",
                alamat="Jl. Sukajadi No. 12",
                id_keluarga=keluarga.id,
                penghasilan=Decimal("5000000.00"),
                jumlah_tanggungan=1,
                nilai_aset=Decimal("30000000.00"),
                tanggal_lahir=datetime.date(1985, 2, 2)
            )
            db.session.add(warga_tidak_layak)
            db.session.commit()

            # Simpan ID primitif untuk mencegah DetachedInstanceError
            self.admin_id = admin.id
            self.petugas_id = petugas.id
            self.keluarga_id = keluarga.id
            self.program_id = program.id
            self.warga_layak_id = warga_layak.id
            self.warga_tidak_layak_id = warga_tidak_layak.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # =========================================================================
    # 4 SKENARIO UTAMA UNIT TEST FUNGSI jalankan_verifikasi
    # =========================================================================

    def test_jalankan_verifikasi_layak(self):
        """Skenario 1: Evaluasi warga yang memenuhi kriteria menghasilkan status 'layak'."""
        with self.app.app_context():
            verif = jalankan_verifikasi(self.warga_layak_id, self.program_id, id_petugas=self.petugas_id)

            self.assertIsNotNone(verif.id)
            self.assertEqual(verif.status_otomatis, "layak")
            self.assertEqual(verif.status_sistem, "layak")
            self.assertIsNone(verif.status_final)
            self.assertIsNone(verif.tanggal_konfirmasi)

            # Audit breakdown
            detail = verif.detail_pengecekan
            self.assertTrue(detail["kriteria_pengecekan"]["penghasilan"]["lolos"])
            self.assertTrue(detail["kriteria_pengecekan"]["tanggungan"]["lolos"])
            self.assertTrue(detail["kriteria_pengecekan"]["aset"]["lolos"])

    def test_jalankan_verifikasi_tidak_layak(self):
        """Skenario 2: Evaluasi warga yang melebihi batas menghasilkan status 'tidak_layak'."""
        with self.app.app_context():
            verif = jalankan_verifikasi(self.warga_tidak_layak_id, self.program_id, id_petugas=self.petugas_id)

            self.assertIsNotNone(verif.id)
            self.assertEqual(verif.status_otomatis, "tidak_layak")
            self.assertIsNone(verif.status_final)

            detail = verif.detail_pengecekan
            self.assertFalse(detail["kriteria_pengecekan"]["penghasilan"]["lolos"])
            self.assertFalse(detail["kriteria_pengecekan"]["tanggungan"]["lolos"])
            self.assertFalse(detail["kriteria_pengecekan"]["aset"]["lolos"])

    def test_jalankan_verifikasi_perlu_ditinjau_data_kosong(self):
        """Skenario 3: Jika ada field warga relevan yang kosong -> status 'perlu_ditinjau' & catat field kurang."""
        with self.app.app_context():
            # Masukkan data warga dengan alamat kosong secara langsung ke database
            db.session.execute(
                db.text(
                    "INSERT INTO warga (id, id_keluarga, nik, nama, alamat, penghasilan, jumlah_tanggungan, nilai_aset, tanggal_lahir) "
                    "VALUES (999, :id_k, '3201019900112233', 'Warga Kurang', '', 1000000.0, 2, 0.0, '1995-05-05')"
                ),
                {"id_k": self.keluarga_id}
            )
            db.session.commit()

            verif = jalankan_verifikasi(999, self.program_id, id_petugas=self.petugas_id)

            self.assertEqual(verif.status_otomatis, "perlu_ditinjau")
            self.assertIn("alamat", verif.detail_pengecekan["field_kurang"])

    def test_jalankan_verifikasi_tolak_sudah_terdaftar(self):
        """Skenario 4: Tolak proses jika warga sudah pernah terdaftar (layak/perlu_ditinjau) pada program yang sama."""
        with self.app.app_context():
            # Verifikasi pertama kali berhasil
            jalankan_verifikasi(self.warga_layak_id, self.program_id, id_petugas=self.petugas_id)

            # Verifikasi kedua kali pada warga & program yang sama harus ditolak dengan error
            with self.assertRaises(AlreadyVerifiedError):
                jalankan_verifikasi(self.warga_layak_id, self.program_id, id_petugas=self.petugas_id)

    # =========================================================================
    # UNIT TEST TAMBAHAN (ENDPOINT, RBAC, FORM & KONFIRMASI)
    # =========================================================================

    def test_konfirmasi_hanya_bisa_sekali(self):
        """Uji coba aturan: Petugas mengisi status_final, HANYA BISA SEKALI (tolak jika tanggal_konfirmasi sudah terisi)."""
        # Login sebagai petugas
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})

        with self.app.app_context():
            verif = jalankan_verifikasi(self.warga_layak_id, self.program_id, id_petugas=self.petugas_id)
            verif_id = verif.id

        # Konfirmasi pertama kali: Berhasil
        res1 = self.client.post(f"/verifikasi/{verif_id}/konfirmasi", data={
            "status_final": "layak",
            "catatan_petugas": "Telah disurvei dan disetujui."
        }, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)

        with self.app.app_context():
            v_check = db.session.get(Verifikasi, verif_id)
            self.assertEqual(v_check.status_final, "layak")
            self.assertIsNotNone(v_check.tanggal_konfirmasi)

        # Konfirmasi kedua kali: Ditolak (pesan flash error)
        res2 = self.client.post(f"/verifikasi/{verif_id}/konfirmasi", data={
            "status_final": "tidak_layak",
            "catatan_petugas": "Coba ubah status lagi"
        }, follow_redirects=True)
        self.assertIn(b"sudah pernah dikonfirmasi", res2.data)

    def test_role_access_control_petugas_forbidden_program_tambah(self):
        """Petugas verifikasi tidak memiliki hak untuk menambah program bantuan (403 Forbidden)."""
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})
        res = self.client.get("/program/tambah")
        self.assertEqual(res.status_code, 403)
        self.assertIn(b"403", res.data)
        self.assertIn(b"Akses Ditolak", res.data)

    def test_warga_inline_validation_error(self):
        """Form warga harus menampilkan pesan error inline jika NIK tidak tepat 16 digit."""
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})
        res = self.client.post("/warga/tambah", data={
            "nik": "12345",  # Invalid: hanya 5 digit
            "id_keluarga": self.keluarga_id,
            "nama": "Tester Invalid",
            "alamat": "Jl. Uji Coba",
            "tanggal_lahir": "1995-01-01",
            "penghasilan": "1000000",
            "jumlah_tanggungan": "1",
            "nilai_aset": "0"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"is-invalid", res.data)
        self.assertIn(b"NIK harus tepat 16 digit", res.data)

    def test_program_crud_admin(self):
        """Admin dapat membuat dan memperbarui master program bantuan sosial."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # 1. Tambah program baru
        res_tambah = self.client.post("/program/tambah", data={
            "nama_program": "Bansos Sembako",
            "kriteria_penghasilan_max": "1500000.00",
            "kriteria_tanggungan_min": "1",
            "kriteria_aset_max": "10000000.00",
            "deskripsi": "Bantuan sembako bulanan"
        }, follow_redirects=True)
        self.assertEqual(res_tambah.status_code, 200)
        self.assertIn(b"Bansos Sembako", res_tambah.data)

        # 2. Edit program yang baru dibuat
        with self.app.app_context():
            prog = ProgramBantuan.query.filter_by(nama_program="Bansos Sembako").first()
            prog_id = prog.id

        res_edit = self.client.post(f"/program/{prog_id}/edit", data={
            "nama_program": "Bansos Sembako Diperbarui",
            "kriteria_penghasilan_max": "1800000.00",
            "kriteria_tanggungan_min": "2",
            "kriteria_aset_max": "12000000.00",
            "deskripsi": "Deskripsi baru"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b"Bansos Sembako Diperbarui", res_edit.data)

    def test_verifikasi_flow_via_form(self):
        """Menjalankan evaluasi verifikasi melalui form POST /verifikasi/mulai."""
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})
        res = self.client.post("/verifikasi/mulai", data={
            "id_warga": self.warga_layak_id,
            "id_program": self.program_id,
            "catatan": "Verifikasi formulir test"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"LAYAK", res.data)
        self.assertIn(b"Detail Audit Verifikasi", res.data)

    def test_custom_404_page(self):
        """Halaman 404 khusus harus tampil ketika mengakses route yang tidak ada."""
        res = self.client.get("/halaman-yang-pasti-tidak-ada")
        self.assertEqual(res.status_code, 404)
        self.assertIn(b"404", res.data)
        self.assertIn(b"Halaman Tidak Ditemukan", res.data)

    def test_registrasi_warga_sukses(self):
        """Warga dapat mendaftar akun baru dan otomatis memiliki role warga."""
        res = self.client.post("/auth/register", data={
            "nama": "Warga Baru Mandiri",
            "nik": "3201010101900001",
            "username": "wargabaru",
            "password": "password123",
            "konfirmasi_password": "password123"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Pendaftaran berhasil", res.data)

        with self.app.app_context():
            u = User.query.filter_by(username="wargabaru").first()
            self.assertIsNotNone(u)
            self.assertEqual(u.role, "warga")
            self.assertEqual(u.nik, "3201010101900001")
            self.assertTrue(u.is_warga)
            self.assertFalse(u.is_admin)

    def test_registrasi_warga_mismatch_password(self):
        """Validasi inline menolak pendaftaran jika konfirmasi password tidak cocok."""
        res = self.client.post("/auth/register", data={
            "nama": "Warga Mismatch",
            "nik": "3201010101900002",
            "username": "wargabeda",
            "password": "password123",
            "konfirmasi_password": "passwordBERBEDA"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"is-invalid", res.data)
        self.assertIn(b"Konfirmasi password tidak cocok", res.data)

    def test_dashboard_warga_view(self):
        """Pengguna dengan role warga melihat dashboard portal warga dengan status bansos miliknya."""
        # 1. Daftarkan warga
        self.client.post("/auth/register", data={
            "nama": "Budi Layak",
            "nik": "3201010101900001",
            "username": "budilayak",
            "password": "password123",
            "konfirmasi_password": "password123"
        }, follow_redirects=True)

        # 2. Login sebagai warga
        self.client.post("/auth/login", data={"username": "budilayak", "password": "password123"})

        # 3. Buka dashboard
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Portal Warga", res.data)
        self.assertIn(b"Status Verifikasi Bantuan Sosial Saya", res.data)
        self.assertIn(b"Data Kependudukan", res.data)

    # =========================================================================
    # SKENARIO PENGUJIAN DESIL & PENGAJUAN PERUBAHAN DESIL
    # =========================================================================

    def test_desil_metadata_dan_auto_calculation(self):
        """Validasi metadata Desil 1-10 dan algoritma penghitungan otomatis berbasis penghasilan & aset."""
        self.assertEqual(len(DESIL_INFO), 10)
        
        # Desil 1-4 layak bansos
        self.assertTrue(get_desil_info(1)["is_layak_bansos"])
        self.assertTrue(get_desil_info(2)["is_layak_bansos"])
        self.assertTrue(get_desil_info(3)["is_layak_bansos"])
        self.assertTrue(get_desil_info(4)["is_layak_bansos"])
        
        # Desil 5-10 tidak layak bansos
        self.assertFalse(get_desil_info(5)["is_layak_bansos"])
        self.assertFalse(get_desil_info(7)["is_layak_bansos"])
        self.assertFalse(get_desil_info(10)["is_layak_bansos"])

        # Properti keterangan_desil pada model Warga
        with self.app.app_context():
            w = db.session.get(Warga, self.warga_layak_id)
            w.desil = 1
            info = w.keterangan_desil
            self.assertIn("Sangat Miskin", info["kategori"])
            self.assertTrue(info["is_layak_bansos"])
            self.assertIn("rumah_desil1", w.foto_rumah_url)

            # Auto-kalkulasi desil pada instance warga jika desil belum diset
            w.desil = None
            w.penghasilan = Decimal("800000.00")
            w.jumlah_tanggungan = 2
            self.assertEqual(w.hitung_desil_otomatis(), 1)

            w.penghasilan = Decimal("1500000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 2)

            w.penghasilan = Decimal("2500000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 3)

            w.penghasilan = Decimal("3500000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 4)

            w.penghasilan = Decimal("4500000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 5)

            w.penghasilan = Decimal("8000000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 7)

            w.penghasilan = Decimal("18000000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 9)

            w.penghasilan = Decimal("30000000.00")
            w.jumlah_tanggungan = 0
            self.assertEqual(w.hitung_desil_otomatis(), 10)

    def test_auto_desil_multi_parameter_aset_dan_api(self):
        """Kalkulasi otomatis desil berbasis aset fisik, daya listrik, kendaraan, dan API endpoint."""
        with self.app.app_context():
            # 1. Warga berpenghasilan rendah (1.000.000) tapi memiliki mobil & listrik 2200 VA -> minimal Desil 7 (Mampu)
            w_mobil = Warga(
                nik="3201017777770001",
                nama="Warga Punya Mobil",
                alamat="Jl. Cemara No. 1",
                id_keluarga=self.keluarga_id,
                penghasilan=Decimal("1000000.00"),
                jumlah_tanggungan=2,
                jenis_kendaraan="mobil",
                jumlah_kendaraan=1,
                daya_listrik=2200,
                status_rumah="milik_sendiri",
                tanggal_lahir=datetime.date(1988, 1, 1)
            )
            self.assertGreaterEqual(w_mobil.hitung_desil_otomatis(), 7)

            # 2. Warga menumpang, non-PLN (0 VA), tanpa kendaraan -> Desil 1 atau 2
            w_rentan = Warga(
                nik="3201017777770002",
                nama="Warga Sangat Rentan",
                alamat="Jl. Gang Sempit No. 2",
                id_keluarga=self.keluarga_id,
                penghasilan=Decimal("750000.00"),
                jumlah_tanggungan=3,
                status_rumah="menumpang",
                daya_listrik=0,
                jenis_kendaraan="tidak_ada",
                tanggal_lahir=datetime.date(1993, 2, 2)
            )
            self.assertLessEqual(w_rentan.hitung_desil_otomatis(), 2)

            # 3. Method static kalkulasi_desil_lengkap mengembalikan metadata lengkap (Desil 2 untuk per kapita Rp 1.500.000)
            hasil = Warga.kalkulasi_desil_lengkap(
                penghasilan=1500000,
                jumlah_tanggungan=0,
                status_rumah="sewa_kontrak",
                luas_tanah=30,
                daya_listrik=450,
                jenis_kendaraan="motor",
                jumlah_kendaraan=1
            )
            self.assertEqual(hasil["desil"], 2)
            self.assertIn("Miskin", hasil["kategori"])
            self.assertTrue(hasil["is_layak_bansos"])

        # 4. Pengujian API Endpoint /warga/api/hitung-desil
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(self.admin_id)
            sess["_fresh"] = True

        # 4a. Pengujian tanpa foto rumah (harus belum lengkap dan desil None)
        resp_tanpa_foto = client.post("/warga/api/hitung-desil", json={
            "penghasilan": 1500000,
            "jumlah_tanggungan": 0,
            "status_rumah": "sewa_kontrak",
            "luas_tanah": 30,
            "daya_listrik": 450,
            "jenis_kendaraan": "motor",
            "jumlah_kendaraan": 1,
            "has_foto": False
        })
        self.assertEqual(resp_tanpa_foto.status_code, 200)
        data_tanpa_foto = resp_tanpa_foto.get_json()
        self.assertTrue(data_tanpa_foto["success"])
        self.assertFalse(data_tanpa_foto["lengkap"])
        self.assertIsNone(data_tanpa_foto["desil"])
        self.assertIn("Lengkapi seluruh data", data_tanpa_foto["pesan"])

        # 4b. Pengujian dengan foto rumah dan seluruh data lengkap (harus sukses dan terhitung desil)
        resp = client.post("/warga/api/hitung-desil", json={
            "penghasilan": 1500000,
            "jumlah_tanggungan": 0,
            "status_rumah": "sewa_kontrak",
            "luas_tanah": 30,
            "daya_listrik": 450,
            "jenis_kendaraan": "motor",
            "jumlah_kendaraan": 1,
            "has_foto": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["lengkap"])
        self.assertEqual(data["desil"], 2)

    def test_engine_verifikasi_kriteria_desil_max(self):
        """Rule engine menolak warga jika desilnya melebihi kriteria_desil_max program."""
        with self.app.app_context():
            # Set program hanya untuk Desil <= 3
            prog = db.session.get(ProgramBantuan, self.program_id)
            prog.kriteria_desil_max = 3
            db.session.commit()

            # Buat warga dengan desil 7 (terdata mampu) meskipun gaji & aset kecil
            warga_salah_desil = Warga(
                nik="3201019999990001",
                nama="Warga Salah Desil",
                alamat="Jl. Sempit No. 5",
                id_keluarga=self.keluarga_id,
                penghasilan=Decimal("900000.00"),
                jumlah_tanggungan=3,
                nilai_aset=Decimal("4000000.00"),
                desil=7,
                tanggal_lahir=datetime.date(1990, 1, 1)
            )
            db.session.add(warga_salah_desil)
            db.session.commit()
            w_id = warga_salah_desil.id

            # Verifikasi dijalankan dalam app_context: harus TIDAK LAYAK karena desil 7 > 3
            hasil = jalankan_verifikasi(w_id, self.program_id)
            self.assertEqual(hasil.status_otomatis, "tidak_layak")
            self.assertFalse(hasil.detail_pengecekan["kriteria_pengecekan"]["desil"]["lolos"])
            self.assertIn("melebihi batas maksimal program (Maksimal Desil 3)", hasil.detail_pengecekan["ringkasan"])
            self.assertIn("Desil 7", hasil.detail_pengecekan["ringkasan"])

    def test_pengajuan_perubahan_desil_oleh_warga(self):
        """Warga yang desilnya salah dapat mengajukan permohonan perubahan desil dengan bukti foto rumah."""
        # 1. Buat data warga dengan Desil 7
        with self.app.app_context():
            warga = Warga(
                nik="3201018888880001",
                nama="Ratna Sanggah",
                alamat="Kampung Cibaduyut",
                id_keluarga=self.keluarga_id,
                penghasilan=Decimal("850000.00"),
                jumlah_tanggungan=2,
                nilai_aset=Decimal("3000000.00"),
                desil=7,
                tanggal_lahir=datetime.date(1992, 3, 3)
            )
            db.session.add(warga)
            db.session.commit()
            w_id = warga.id

        # 2. Registrasi akun user warga
        self.client.post("/auth/register", data={
            "nama": "Ratna Sanggah",
            "nik": "3201018888880001",
            "username": "ratna_sanggah",
            "password": "password123",
            "konfirmasi_password": "password123"
        }, follow_redirects=True)

        # 3. Login warga
        self.client.post("/auth/login", data={"username": "ratna_sanggah", "password": "password123"})

        # 4. GET form ajukan perubahan desil
        res_get = self.client.get("/pengajuan-desil/ajukan")
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b"Pengajuan Perubahan Desil", res_get.data)
        self.assertIn(b"Desil 7", res_get.data)

        # 5. POST pengajuan perubahan desil ke Desil 1 beserta bukti foto rumah
        dummy_photo = (io.BytesIO(b"dummy image data"), "rumah_bilik.jpg")
        res_post = self.client.post("/pengajuan-desil/ajukan", data={
            "desil_diajukan": 1,
            "penghasilan_terkini": "850000.00",
            "jumlah_tanggungan": 2,
            "foto_rumah": dummy_photo,
            "alasan_pengajuan": "Data kelurahan tercatat Desil 7 padahal kondisi riil tergolong miskin penghasilan buruh cuci."
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn(b"Permohonan perubahan desil berhasil diajukan", res_post.data)

        # 6. Periksa data tersimpan di database
        with self.app.app_context():
            pengajuan = PengajuanDesil.query.filter_by(id_warga=w_id).first()
            self.assertIsNotNone(pengajuan)
            self.assertEqual(pengajuan.desil_lama, 7)
            self.assertEqual(pengajuan.desil_diajukan, 1)
            self.assertEqual(pengajuan.status, "menunggu")
            self.assertIn("uploads/rumah/", pengajuan.foto_rumah_baru)

        # 7. Cek riwayat warga
        res_riwayat = self.client.get("/pengajuan-desil/saya")
        self.assertEqual(res_riwayat.status_code, 200)
        self.assertIn(b"Menunggu Verifikasi", res_riwayat.data)
        self.assertIn(b"Desil 1", res_riwayat.data)

    def test_petugas_setujui_perubahan_desil_dan_verifikasi_bansos_lolos(self):
        """Persetujuan petugas otomatis memperbarui desil & penghasilan warga dan meloloskan bansos."""
        with self.app.app_context():
            # Setup program PKH (maks desil 3)
            prog = db.session.get(ProgramBantuan, self.program_id)
            prog.kriteria_desil_max = 3

            # Buat warga terdata Desil 7
            warga = Warga(
                nik="3201017777770001",
                nama="Bambang Kurang Mampu",
                alamat="Jl. Cikutra No. 9",
                id_keluarga=self.keluarga_id,
                penghasilan=Decimal("800000.00"),
                jumlah_tanggungan=3,
                nilai_aset=Decimal("3000000.00"),
                desil=7,
                tanggal_lahir=datetime.date(1989, 4, 4)
            )
            db.session.add(warga)
            db.session.flush()

            # Buat pengajuan perubahan ke Desil 1
            pengajuan = PengajuanDesil(
                id_warga=warga.id,
                id_user=self.admin_id,
                desil_lama=7,
                desil_diajukan=1,
                penghasilan_terkini=Decimal("800000.00"),
                jumlah_tanggungan=3,
                foto_rumah_baru="uploads/rumah/test_rumah.jpg",
                alasan_pengajuan="Data desil 7 keliru, kondisi keluarga tergolong miskin ekstrem.",
                status="menunggu",
                tanggal_pengajuan=datetime.datetime.now()
            )
            db.session.add(pengajuan)
            db.session.commit()
            p_id = pengajuan.id
            w_id = warga.id

        # Petugas login
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})

        # Petugas melihat antrean pengajuan
        res_list = self.client.get("/pengajuan-desil")
        self.assertEqual(res_list.status_code, 200)
        self.assertIn(b"Bambang Kurang Mampu", res_list.data)

        # Petugas menyetujui pengajuan
        res_approve = self.client.post(f"/pengajuan-desil/{p_id}", data={
            "status": "disetujui",
            "desil_disetujui": 1,
            "catatan_petugas": "Telah disurvei langsung, kondisi fisik rumah dan slip gaji terbukti sesuai Desil 1."
        }, follow_redirects=True)
        self.assertEqual(res_approve.status_code, 200)
        self.assertIn(b"disetujui", res_approve.data)

        # Verifikasi data profil warga ter-update
        with self.app.app_context():
            w = db.session.get(Warga, w_id)
            self.assertEqual(w.desil, 1)
            self.assertEqual(w.penghasilan, Decimal("800000.00"))
            self.assertEqual(w.foto_rumah, "uploads/rumah/test_rumah.jpg")

            p = db.session.get(PengajuanDesil, p_id)
            self.assertEqual(p.status, "disetujui")

            # Uji verifikasi bansos: sekarang harus lolos LAYAK karena desil sudah 1 <= 3!
            hasil = jalankan_verifikasi(w_id, self.program_id)
            self.assertEqual(hasil.status_otomatis, "layak")
            self.assertTrue(hasil.detail_pengecekan["kriteria_pengecekan"]["desil"]["lolos"])

    def test_petugas_tolak_pengajuan_desil(self):
        """Penolakan perubahan desil oleh petugas tidak mengubah data desil profil warga."""
        with self.app.app_context():
            warga = Warga(
                nik="3201016666660001",
                nama="Warga Ditolak",
                alamat="Jl. Mewah No. 1",
                id_keluarga=self.keluarga_id,
                penghasilan=Decimal("6000000.00"),
                jumlah_tanggungan=1,
                nilai_aset=Decimal("80000000.00"),
                desil=8,
                tanggal_lahir=datetime.date(1987, 5, 5)
            )
            db.session.add(warga)
            db.session.flush()

            pengajuan = PengajuanDesil(
                id_warga=warga.id,
                id_user=self.admin_id,
                desil_lama=8,
                desil_diajukan=2,
                penghasilan_terkini=Decimal("1500000.00"),
                jumlah_tanggungan=1,
                foto_rumah_baru="uploads/rumah/test_rumah.jpg",
                alasan_pengajuan="Mengajukan perubahan desil ke desil 2.",
                status="menunggu",
                tanggal_pengajuan=datetime.datetime.now()
            )
            db.session.add(pengajuan)
            db.session.commit()
            p_id = pengajuan.id
            w_id = warga.id

        # Petugas login
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})

        # Petugas menolak pengajuan
        res_reject = self.client.post(f"/pengajuan-desil/{p_id}", data={
            "status": "ditolak",
            "desil_disetujui": 8,
            "catatan_petugas": "Kondisi rumah mewah dan aset bernilai tinggi, pengajuan ditolak."
        }, follow_redirects=True)
        self.assertEqual(res_reject.status_code, 200)

        with self.app.app_context():
            p = db.session.get(PengajuanDesil, p_id)
            self.assertEqual(p.status, "ditolak")
            w = db.session.get(Warga, w_id)
            # Desil tetap 8, tidak berubah!
            self.assertEqual(w.desil, 8)

    def test_hak_akses_antrean_pengajuan_desil(self):
        """Warga publik tidak memiliki hak akses membuka antrean review petugas."""
        # Daftarkan dan login warga
        self.client.post("/auth/register", data={
            "nama": "Warga Awam",
            "nik": "3201010101900001",
            "username": "wargaawam",
            "password": "password123",
            "konfirmasi_password": "password123"
        }, follow_redirects=True)
        self.client.post("/auth/login", data={"username": "wargaawam", "password": "password123"})

        # Coba buka antrean verifikasi petugas (role_required admin & petugas_verifikasi)
        res = self.client.get("/pengajuan-desil", follow_redirects=True)
        self.assertEqual(res.status_code, 403)
        self.assertIn(b"403", res.data)
        self.assertIn(b"Akses Ditolak", res.data)


    # =========================================================================
    # PENGUJIAN ROLE PENGGUNA, AKSES KONTROL & KELOLA PETUGAS
    # =========================================================================

    def test_pemisahan_role_dan_akses_dashboard(self):
        """Pengujian pemisahan role: Admin, Petugas, dan Warga ke dashboard masing-masing."""
        # 1. Admin login -> dashboard utama admin
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res_admin = self.client.get("/dashboard")
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b"Dashboard Ikhtisar Verifikasi Bansos", res_admin.data)
        self.client.get("/auth/logout")

        # 2. Petugas login -> dashboard utama petugas
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})
        res_petugas = self.client.get("/dashboard")
        self.assertEqual(res_petugas.status_code, 200)
        self.assertIn(b"Dashboard Ikhtisar Verifikasi Bansos", res_petugas.data)
        self.client.get("/auth/logout")

        # 3. Warga login -> dashboard portal warga
        with self.app.app_context():
            user_w = User(username="warga_test", nama="Ratna Sari", role="warga", nik="3201010505910005")
            user_w.set_password("warga123")
            db.session.add(user_w)
            db.session.commit()

        self.client.post("/auth/login", data={"username": "warga_test", "password": "warga123"})
        res_warga = self.client.get("/dashboard")
        self.assertEqual(res_warga.status_code, 200)
        self.assertIn(b"Portal Warga", res_warga.data)
        self.assertIn(b"Status Bansos Saya", res_warga.data)
        self.client.get("/auth/logout")

    def test_halaman_kelola_petugas_hanya_tampilkan_admin_dan_petugas(self):
        """Halaman Kelola Petugas hanya menampilkan ADMINISTRATOR dan PETUGAS VERIFIKASI, akun warga tidak boleh muncul."""
        with self.app.app_context():
            # Seed akun warga: Ratna Sari, Bambang Sudarmono, Annisa Izzah
            w1 = User(username="warga_ratna", nama="Ratna Sari", role="warga", nik="3201010505910005")
            w1.set_password("warga123")
            w2 = User(username="warga_bambang", nama="Bambang Sudarmono", role="warga", nik="3201010101900001")
            w2.set_password("warga123")
            w3 = User(username="nailong", nama="Annisa Izzah", role="warga", nik="1234567891011121")
            w3.set_password("warga123")
            db.session.add_all([w1, w2, w3])
            db.session.commit()

        # Login sebagai Administrator
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.get("/auth/petugas")
        self.assertEqual(res.status_code, 200)

        # Admin & Petugas HARUS muncul
        self.assertIn(b"Admin Test", res.data)
        self.assertIn(b"Petugas Test", res.data)
        self.assertIn(b"ADMINISTRATOR", res.data)
        self.assertIn(b"PETUGAS VERIFIKASI", res.data)

        # Warga (Ratna Sari, Bambang Sudarmono, Annisa Izzah) TIDAK BOLEH muncul
        self.assertNotIn(b"Ratna Sari", res.data)
        self.assertNotIn(b"warga_ratna", res.data)
        self.assertNotIn(b"Bambang Sudarmono", res.data)
        self.assertNotIn(b"warga_bambang", res.data)
        self.assertNotIn(b"Annisa Izzah", res.data)
        self.assertNotIn(b"nailong", res.data)

    def test_admin_dapat_tambah_petugas_baru_dan_muncul_di_daftar(self):
        """Admin dapat menambahkan akun petugas baru dan langsung muncul di Kelola Petugas."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Tambahkan petugas verifikasi baru
        res = self.client.post("/auth/petugas/tambah", data={
            "nama": "Siti Verifikator",
            "username": "petugas_siti",
            "password": "password123",
            "role": "petugas_verifikasi"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"berhasil didaftarkan", res.data)
        self.assertIn(b"Siti Verifikator", res.data)
        self.assertIn(b"petugas_siti", res.data)
        self.assertIn(b"PETUGAS VERIFIKASI", res.data)

        with self.app.app_context():
            u = User.query.filter_by(username="petugas_siti").first()
            self.assertIsNotNone(u)
            self.assertEqual(u.role, "petugas_verifikasi")
            self.assertTrue(u.is_petugas)

    def test_warga_dilarang_akses_halaman_petugas_dan_admin(self):
        """Akun warga ditolak (403 Forbidden) saat mencoba mengakses URL admin/petugas secara langsung."""
        with self.app.app_context():
            uw = User(username="warga_cek", nama="Warga Cek", role="warga")
            uw.set_password("pass123")
            db.session.add(uw)
            db.session.commit()

        self.client.post("/auth/login", data={"username": "warga_cek", "password": "pass123"})

        # Halaman khusus admin
        res_petugas = self.client.get("/auth/petugas")
        self.assertEqual(res_petugas.status_code, 403)

        # Halaman khusus admin & petugas
        res_warga = self.client.get("/warga")
        self.assertEqual(res_warga.status_code, 403)

        res_verif = self.client.get("/verifikasi/riwayat")
        self.assertEqual(res_verif.status_code, 403)

        res_mulai = self.client.get("/verifikasi/mulai")
        self.assertEqual(res_mulai.status_code, 403)

        res_antrean = self.client.get("/pengajuan-desil")
        self.assertEqual(res_antrean.status_code, 403)

    def test_petugas_dilarang_akses_fitur_administrator(self):
        """Akun petugas verifikasi ditolak (403 Forbidden) saat mencoba mengakses fitur khusus admin."""
        self.client.post("/auth/login", data={"username": "petugas1", "password": "petugas123"})

        # Petugas tidak boleh kelola petugas
        res_petugas = self.client.get("/auth/petugas")
        self.assertEqual(res_petugas.status_code, 403)

        # Petugas tidak boleh tambah/edit/hapus program
        res_prog_tambah = self.client.get("/program/tambah")
        self.assertEqual(res_prog_tambah.status_code, 403)

        res_prog_edit = self.client.get(f"/program/{self.program_id}/edit")
        self.assertEqual(res_prog_edit.status_code, 403)

        res_prog_hapus = self.client.post(f"/program/{self.program_id}/hapus")
        self.assertEqual(res_prog_hapus.status_code, 403)

    def test_registrasi_warga_tidak_bisa_memanipulasi_role(self):
        """Form registrasi mandiri selalu menghasilkan role 'warga', request manipulasi role diabaikan."""
        res = self.client.post("/auth/register", data={
            "nama": "Hacker Role",
            "username": "hacker1",
            "password": "password123",
            "konfirmasi_password": "password123",
            "role": "admin"  # Percobaan manipulasi payload
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            u = User.query.filter_by(username="hacker1").first()
            self.assertIsNotNone(u)
            self.assertEqual(u.role, "warga")
            self.assertFalse(u.is_admin)
            self.assertFalse(u.is_petugas)

    def test_admin_tidak_bisa_hapus_akun_sendiri(self):
        """Admin tidak diizinkan menghapus akun miliknya sendiri."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.post(f"/auth/petugas/{self.admin_id}/hapus", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"tidak dapat menghapus akun Anda sendiri", res.data)

        with self.app.app_context():
            admin = db.session.get(User, self.admin_id)
            self.assertIsNotNone(admin)

    def test_query_terpisah_daftar_akun_warga(self):
        """Query terpisah khusus akun warga hanya mengambil user dengan role WARGA."""
        with self.app.app_context():
            w1 = User(username="warga1", nama="Warga Satu", role="warga")
            w1.set_password("pass123")
            w2 = User(username="warga2", nama="Warga Dua", role="warga")
            w2.set_password("pass123")
            db.session.add_all([w1, w2])
            db.session.commit()

        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.get("/auth/users/warga", headers={"Accept": "application/json"})
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data["success"])
        roles = [u["role"] for u in json_data["users"]]
        self.assertTrue(all(r == "warga" for r in roles))
        self.assertNotIn("admin", roles)
        self.assertNotIn("petugas_verifikasi", roles)

    # =========================================================================
    # PENGUJIAN FITUR HYBRID INPUT LUAS BANGUNAN & VALIDASI
    # =========================================================================

    def test_hybrid_input_luas_bangunan_manual_dan_database(self):
        """Pengguna mengetik luas 36 secara manual dan tersimpan di database."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.post("/warga/tambah", data={
            "nik": "3201010101900010",
            "nama": "Warga Luas Manual",
            "alamat": "Jl. Mawar No. 10",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "1500000",
            "jumlah_tanggungan": "2",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "36",
            "daya_listrik": "450",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1990-01-01"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            w = Warga.query.filter_by(nik="3201010101900010").first()
            self.assertIsNotNone(w)
            self.assertEqual(float(w.luas_tanah), 36.0)

    def test_hybrid_input_luas_bangunan_quick_choice_kos(self):
        """Pengguna memilih tombol 12 m² (Kos), nilai numerik 12 tersimpan tanpa label teks."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.post("/warga/tambah", data={
            "nik": "3201010101900011",
            "nama": "Warga Anak Kos",
            "alamat": "Jl. Melati No. 12",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "1000000",
            "jumlah_tanggungan": "1",
            "status_rumah": "sewa_kontrak",
            "luas_tanah": "12",
            "daya_listrik": "450",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1995-05-05"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            w = Warga.query.filter_by(nik="3201010101900011").first()
            self.assertIsNotNone(w)
            self.assertEqual(float(w.luas_tanah), 12.0)

    def test_hybrid_input_luas_bangunan_pilih_45_lalu_ganti_ke_48(self):
        """Pengguna memilih 45 m² lalu mengganti nilainya secara manual menjadi 48."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.post("/warga/tambah", data={
            "nik": "3201010101900012",
            "nama": "Warga Luas 48",
            "alamat": "Jl. Anggrek No. 48",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "2000000",
            "jumlah_tanggungan": "2",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "48",
            "daya_listrik": "900",
            "jenis_kendaraan": "motor",
            "jumlah_kendaraan": "1",
            "nilai_aset": "0",
            "tanggal_lahir": "1988-08-08"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            w = Warga.query.filter_by(nik="3201010101900012").first()
            self.assertIsNotNone(w)
            self.assertEqual(float(w.luas_tanah), 48.0)

    def test_hybrid_input_luas_bangunan_kalkulator_desimal_panjang_lebar(self):
        """Pengguna menghitung dengan kalkulator: 6x6=36, 5x9=45, dan 4x5.25=21 (desimal)."""
        # Verifikasi formula perkalian
        self.assertEqual(round(6.0 * 6.0, 2), 36.0)
        self.assertEqual(round(5.0 * 9.0, 2), 45.0)
        self.assertEqual(round(4.0 * 5.25, 2), 21.0)

        # Simpan nilai luas desimal (contoh: 52.25)
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        res = self.client.post("/warga/tambah", data={
            "nik": "3201010101900013",
            "nama": "Warga Luas Desimal",
            "alamat": "Jl. Dahlia No. 21",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "2500000",
            "jumlah_tanggungan": "2",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "52.25",
            "daya_listrik": "900",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1985-03-15"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            w = Warga.query.filter_by(nik="3201010101900013").first()
            self.assertIsNotNone(w)
            self.assertEqual(float(w.luas_tanah), 52.25)

    def test_validasi_luas_bangunan_nol_negatif_dan_kosong(self):
        """Form menolak luas bangunan nol, negatif, dan kosong."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Kasus 1: Luas 0
        res_zero = self.client.post("/warga/tambah", data={
            "nik": "3201010101900014",
            "nama": "Warga Luas Nol",
            "alamat": "Jl. Cempaka No. 0",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "1000000",
            "jumlah_tanggungan": "1",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "0",
            "daya_listrik": "450",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1990-01-01"
        })
        self.assertEqual(res_zero.status_code, 200)
        with self.app.app_context():
            self.assertIsNone(Warga.query.filter_by(nik="3201010101900014").first())

        # Kasus 2: Luas negatif
        res_neg = self.client.post("/warga/tambah", data={
            "nik": "3201010101900015",
            "nama": "Warga Luas Negatif",
            "alamat": "Jl. Cempaka No. -5",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "1000000",
            "jumlah_tanggungan": "1",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "-25",
            "daya_listrik": "450",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1990-01-01"
        })
        self.assertEqual(res_neg.status_code, 200)
        with self.app.app_context():
            self.assertIsNone(Warga.query.filter_by(nik="3201010101900015").first())

        # Kasus 3: Luas kosong
        res_empty = self.client.post("/warga/tambah", data={
            "nik": "3201010101900016",
            "nama": "Warga Luas Kosong",
            "alamat": "Jl. Cempaka No. Kosong",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "1000000",
            "jumlah_tanggungan": "1",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "",
            "daya_listrik": "450",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1990-01-01"
        })
        self.assertEqual(res_empty.status_code, 200)
        with self.app.app_context():
            self.assertIsNone(Warga.query.filter_by(nik="3201010101900016").first())

    def test_edit_warga_perbarui_luas_bangunan(self):
        """Fitur edit warga dapat membaca luas bangunan tersimpan dan memperbaruinya."""
        self.client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Cek form GET edit membaca nilai luas bangunan dengan benar
        res_get = self.client.get(f"/warga/{self.warga_layak_id}/edit")
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b"Luas Bangunan (m\xc2\xb2)", res_get.data)

        # Update nilai luas bangunan menjadi 70
        res_post = self.client.post(f"/warga/{self.warga_layak_id}/edit", data={
            "nik": "3201010101900001",
            "nama": "Budi Layak Edit",
            "alamat": "Jl. Sukajadi No. 10 Baru",
            "id_keluarga": self.keluarga_id,
            "penghasilan": "1200000",
            "jumlah_tanggungan": "3",
            "status_rumah": "milik_sendiri",
            "luas_tanah": "70",
            "daya_listrik": "900",
            "jenis_kendaraan": "tidak_ada",
            "jumlah_kendaraan": "0",
            "nilai_aset": "0",
            "tanggal_lahir": "1990-01-01"
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        with self.app.app_context():
            w = db.session.get(Warga, self.warga_layak_id)
            self.assertEqual(float(w.luas_tanah), 70.0)

    def test_model_validates_luas_tanah_raise_error(self):
        """Validasi langsung pada model Warga menolak nilai 0, negatif, atau string bukan angka."""
        with self.app.app_context():
            w = Warga(
                nik="3201010101900099",
                nama="Test Validator",
                alamat="Jl. Uji",
                id_keluarga=self.keluarga_id
            )
            # Nilai valid
            w.luas_tanah = 36.5
            self.assertEqual(w.luas_tanah, 36.5)

            # Nilai 0
            with self.assertRaises(ValueError):
                w.luas_tanah = 0

            # Nilai negatif
            with self.assertRaises(ValueError):
                w.luas_tanah = -10.5

            # Nilai non-angka
            with self.assertRaises(ValueError):
                w.luas_tanah = "bukan_angka"


if __name__ == "__main__":
    unittest.main()

