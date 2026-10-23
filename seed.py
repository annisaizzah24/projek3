import os
import datetime
from decimal import Decimal
from app import create_app, db
from app.models import User, Keluarga, Warga, ProgramBantuan, Verifikasi, PengajuanDesil

app = create_app()

def run_seed():
    with app.app_context():
        print("Creating tables if they do not exist...")
        db.create_all()

        print("Seeding Users...")
        # 1. Admin & Petugas
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                nama="Administrator Pusat",
                role="admin"
            )
            admin.set_password("admin123")
            db.session.add(admin)

        petugas = User.query.filter_by(username="petugas1").first()
        if not petugas:
            petugas = User(
                username="petugas1",
                nama="Rudi Hartono (Petugas Lapangan)",
                role="petugas_verifikasi"
            )
            petugas.set_password("petugas123")
            db.session.add(petugas)

        # Akun Warga untuk testing login warga
        user_ratna = User.query.filter_by(username="warga_ratna").first()
        if not user_ratna:
            user_ratna = User(
                username="warga_ratna",
                nama="Ratna Sari",
                role="warga",
                nik="3201010505910005"
            )
            user_ratna.set_password("warga123")
            db.session.add(user_ratna)

        user_bambang = User.query.filter_by(username="warga_bambang").first()
        if not user_bambang:
            user_bambang = User(
                username="warga_bambang",
                nama="Bambang Sudarmono",
                role="warga",
                nik="3201010101900001"
            )
            user_bambang.set_password("warga123")
            db.session.add(user_bambang)

        db.session.commit()

        # 2. Keluarga (Minimal 2 Keluarga)
        print("Seeding Keluarga...")
        k1 = Keluarga.query.filter_by(nomor_kk="3201012345670001").first()
        if not k1:
            k1 = Keluarga(
                nomor_kk="3201012345670001",
                kepala_keluarga="Bambang Sudarmono",
                alamat="Jl. Sukajadi No. 45 RT 01/RW 03, Bandung"
            )
            db.session.add(k1)

        k2 = Keluarga.query.filter_by(nomor_kk="3201012345670002").first()
        if not k2:
            k2 = Keluarga(
                nomor_kk="3201012345670002",
                kepala_keluarga="Slamet Riyadi",
                alamat="Jl. Cibaduyut Raya No. 12 RT 04/RW 02, Bandung"
            )
            db.session.add(k2)

        db.session.commit()

        # 3. Warga (Lengkap dengan desil dan foto_rumah)
        print("Seeding Warga...")
        daftar_warga_data = [
            {
                "id_keluarga": k1.id,
                "nik": "3201010101900001",
                "nama": "Bambang Sudarmono",
                "alamat": "Jl. Sukajadi No. 45 RT 01/RW 03, Bandung",
                "penghasilan": Decimal("1200000.00"),
                "jumlah_tanggungan": 3,
                "nilai_aset": Decimal("6000000.00"),
                "status_rumah": "sewa_kontrak",
                "luas_tanah": 30,
                "daya_listrik": 450,
                "jenis_kendaraan": "motor",
                "jumlah_kendaraan": 1,
                "foto_kendaraan": "images/rumah/motor_sample.svg",
                "desil": 2,
                "foto_rumah": "images/rumah/rumah_desil2_sederhana.svg",
                "tanggal_lahir": datetime.date(1990, 1, 1)
            },
            {
                "id_keluarga": k1.id,
                "nik": "3201010202920002",
                "nama": "Siti Maryam",
                "alamat": "Jl. Sukajadi No. 45 RT 01/RW 03, Bandung",
                "penghasilan": Decimal("0.00"),
                "jumlah_tanggungan": 3,
                "nilai_aset": Decimal("0.00"),
                "status_rumah": "menumpang",
                "luas_tanah": 20,
                "daya_listrik": 450,
                "jenis_kendaraan": "tidak_ada",
                "jumlah_kendaraan": 0,
                "foto_kendaraan": None,
                "desil": 1,
                "foto_rumah": "images/rumah/rumah_desil1_bilik.svg",
                "tanggal_lahir": datetime.date(1992, 2, 2)
            },
            {
                "id_keluarga": k1.id,
                "nik": "3201010303150003",
                "nama": "Dimas Anggara",
                "alamat": "Jl. Sukajadi No. 45 RT 01/RW 03, Bandung",
                "penghasilan": Decimal("0.00"),
                "jumlah_tanggungan": 0,
                "nilai_aset": Decimal("0.00"),
                "status_rumah": "menumpang",
                "luas_tanah": 20,
                "daya_listrik": 450,
                "jenis_kendaraan": "tidak_ada",
                "jumlah_kendaraan": 0,
                "foto_kendaraan": None,
                "desil": 1,
                "foto_rumah": "images/rumah/rumah_desil1_bilik.svg",
                "tanggal_lahir": datetime.date(2015, 3, 3)
            },
            {
                "id_keluarga": k2.id,
                "nik": "3201010404880004",
                "nama": "Slamet Riyadi",
                "alamat": "Jl. Cibaduyut Raya No. 12 RT 04/RW 02, Bandung",
                "penghasilan": Decimal("4800000.00"),
                "jumlah_tanggungan": 1,
                "nilai_aset": Decimal("135000000.00"),
                "status_rumah": "milik_sendiri",
                "luas_tanah": 90,
                "daya_listrik": 2200,
                "jenis_kendaraan": "mobil",
                "jumlah_kendaraan": 1,
                "foto_kendaraan": None,
                "desil": 7,
                "foto_rumah": "images/rumah/rumah_desil7_permanen.svg",
                "tanggal_lahir": datetime.date(1988, 4, 4)
            },
            {
                # Skenario Kasus Khusus: Ratna Sari terdata salah di sistem sebagai Desil 7 (Menengah Cukup),
                # padahal kondisi sebenarnya adalah buruh tidak tetap berpenghasilan Rp 850.000 dengan rumah sederhana.
                "id_keluarga": k2.id,
                "nik": "3201010505910005",
                "nama": "Ratna Sari",
                "alamat": "Jl. Cibaduyut Raya No. 12 RT 04/RW 02, Bandung",
                "penghasilan": Decimal("850000.00"),
                "jumlah_tanggungan": 2,
                "nilai_aset": Decimal("0.00"),
                "status_rumah": "sewa_kontrak",
                "luas_tanah": 24,
                "daya_listrik": 450,
                "jenis_kendaraan": "tidak_ada",
                "jumlah_kendaraan": 0,
                "foto_kendaraan": None,
                "desil": 7,  # Data salah di sistem yang perlu diajukan perubahan
                "foto_rumah": "images/rumah/rumah_desil7_permanen.svg",
                "tanggal_lahir": datetime.date(1991, 5, 5)
            }
        ]

        for w_data in daftar_warga_data:
            w = Warga.query.filter_by(nik=w_data["nik"]).first()
            if not w:
                w = Warga(**w_data)
                db.session.add(w)
            else:
                w.nilai_aset = w_data["nilai_aset"]
                w.desil = w_data["desil"]
                w.foto_rumah = w_data["foto_rumah"]
                w.penghasilan = w_data["penghasilan"]
                w.status_rumah = w_data.get("status_rumah", "milik_sendiri")
                w.luas_tanah = w_data.get("luas_tanah", 36)
                w.daya_listrik = w_data.get("daya_listrik", 450)
                w.jenis_kendaraan = w_data.get("jenis_kendaraan", "tidak_ada")
                w.jumlah_kendaraan = w_data.get("jumlah_kendaraan", 0)
                w.foto_kendaraan = w_data.get("foto_kendaraan")

        db.session.commit()

        # 4. Program Bantuan (dengan kriteria_desil_max)
        print("Seeding Program Bantuan...")
        daftar_program_data = [
            {
                "nama_program": "Program Keluarga Harapan (PKH)",
                "kriteria_penghasilan_max": Decimal("2000000.00"),
                "kriteria_tanggungan_min": 2,
                "kriteria_aset_max": Decimal("15000000.00"),
                "kriteria_desil_max": 3,
                "deskripsi": "Bantuan sosial bersyarat bagi keluarga rentan miskin (Maksimal Desil 3) dengan tanggungan anak sekolah atau balita.",
                "is_active": True
            },
            {
                "nama_program": "Bantuan Pangan Non-Tunai (BPNT)",
                "kriteria_penghasilan_max": Decimal("2500000.00"),
                "kriteria_tanggungan_min": 0,
                "kriteria_aset_max": Decimal("25000000.00"),
                "kriteria_desil_max": 4,
                "deskripsi": "Bantuan pemenuhan pangan sembako pokok setiap bulan bagi warga prasejahtera (Maksimal Desil 4).",
                "is_active": True
            },
            {
                "nama_program": "Bantuan Langsung Tunai (BLT) Kemiskinan Ekstrem",
                "kriteria_penghasilan_max": Decimal("1500000.00"),
                "kriteria_tanggungan_min": 1,
                "kriteria_aset_max": Decimal("10000000.00"),
                "kriteria_desil_max": 2,
                "deskripsi": "Bantuan uang tunai langsung bagi masyarakat kelompok kemiskinan ekstrem (Maksimal Desil 2).",
                "is_active": True
            }
        ]

        for p_data in daftar_program_data:
            p = ProgramBantuan.query.filter_by(nama_program=p_data["nama_program"]).first()
            if not p:
                p = ProgramBantuan(**p_data)
                db.session.add(p)
            else:
                p.kriteria_aset_max = p_data["kriteria_aset_max"]
                p.kriteria_desil_max = p_data["kriteria_desil_max"]
                p.is_active = p_data["is_active"]

        db.session.commit()

        # 5. Verifikasi Contoh
        print("Seeding Contoh Verifikasi...")
        w1 = Warga.query.filter_by(nik="3201010101900001").first()
        w4 = Warga.query.filter_by(nik="3201010404880004").first()
        prog1 = ProgramBantuan.query.filter_by(nama_program="Program Keluarga Harapan (PKH)").first()

        if w1 and prog1 and not Verifikasi.query.filter_by(id_warga=w1.id, id_program=prog1.id).first():
            v1 = Verifikasi(
                id_warga=w1.id,
                id_program=prog1.id,
                id_petugas=petugas.id,
                status_otomatis="layak",
                status_final="layak",
                catatan_petugas="Telah disurvei kondisi rumah sesuai kriteria prasejahtera Desil 2.",
                detail_pengecekan={
                    "kriteria_pengecekan": {
                        "penghasilan": {"nilai": 1200000.0, "batas_maksimal": 2000000.0, "lolos": True},
                        "tanggungan": {"nilai": 3, "batas_minimal": 2, "lolos": True},
                        "aset": {"nilai": 5000000.0, "batas_maksimal": 15000000.0, "lolos": True},
                        "desil": {"nilai": 2, "batas_maksimal": 3, "kategori_warga": "Miskin", "lolos": True}
                    },
                    "field_kurang": [],
                    "ringkasan": "Warga memenuhi seluruh kriteria kelayakan program bantuan (Termasuk Desil 2)."
                },
                tanggal_verifikasi=datetime.datetime.now(),
                tanggal_konfirmasi=datetime.datetime.now()
            )
            db.session.add(v1)

        if w4 and prog1 and not Verifikasi.query.filter_by(id_warga=w4.id, id_program=prog1.id).first():
            v2 = Verifikasi(
                id_warga=w4.id,
                id_program=prog1.id,
                id_petugas=petugas.id,
                status_otomatis="tidak_layak",
                status_final="tidak_layak",
                catatan_petugas="Penghasilan, aset, dan desil (Desil 7) melebihi ketentuan program.",
                detail_pengecekan={
                    "kriteria_pengecekan": {
                        "penghasilan": {"nilai": 4800000.0, "batas_maksimal": 2000000.0, "lolos": False},
                        "tanggungan": {"nilai": 1, "batas_minimal": 2, "lolos": False},
                        "aset": {"nilai": 35000000.0, "batas_maksimal": 15000000.0, "lolos": False},
                        "desil": {"nilai": 7, "batas_maksimal": 3, "kategori_warga": "Menengah Cukup", "lolos": False}
                    },
                    "field_kurang": [],
                    "ringkasan": "Tidak memenuhi kriteria: penghasilan melebihi batas, desil warga (Desil 7) melebihi batas program (Maksimal Desil 3)."
                },
                tanggal_verifikasi=datetime.datetime.now(),
                tanggal_konfirmasi=datetime.datetime.now()
            )
            db.session.add(v2)

        # 6. Seed Contoh Pengajuan Perubahan Desil (Kasus Nyata Ratna Sari: Desil 7 -> Desil 1)
        w5 = Warga.query.filter_by(nik="3201010505910005").first()
        if w5 and not PengajuanDesil.query.filter_by(id_warga=w5.id).first():
            print("Seeding Pengajuan Perubahan Desil Warga (Ratna Sari)...")
            pengajuan_ratna = PengajuanDesil(
                id_warga=w5.id,
                id_user=user_ratna.id,
                desil_lama=7,
                desil_diajukan=1,
                penghasilan_terkini=Decimal("850000.00"),
                jumlah_tanggungan=2,
                foto_rumah_baru="images/rumah/rumah_desil1_bilik.svg",
                dokumen_pendukung=None,
                alasan_pengajuan="Data profil kelurahan tercatat Desil 7 (Menengah Cukup), padahal kondisi keluarga kami sebenarnya tergolong miskin dengan penghasilan buruh cuci Rp 850.000/bulan, 2 anak tanggungan sekolah, dan rumah bilik kayu. Mohon penyesuaian desil ke Desil 1 agar kami memenuhi syarat mendapatkan bantuan PKH.",
                status="menunggu",
                tanggal_pengajuan=datetime.datetime.now()
            )
            db.session.add(pengajuan_ratna)

        db.session.commit()
        print("Database seed completed successfully!")

if __name__ == "__main__":
    run_seed()
