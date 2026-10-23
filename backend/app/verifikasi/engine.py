import os
import logging
import datetime
from decimal import Decimal
from app.extensions import db
from app.models import Warga, ProgramBantuan, Verifikasi, User

# =============================================================================
# SETUP DEDICATED AUDIT LOGGER
# =============================================================================
LOG_DIR = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
AUDIT_LOG_FILE = os.path.join(LOG_DIR, "verifikasi_audit.log")

audit_logger = logging.getLogger("verifikasi_audit")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    fh = logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    audit_logger.addHandler(fh)


class AlreadyVerifiedError(Exception):
    """Exception dilempar jika warga sudah pernah terdaftar pada program yang sama."""
    pass


class NotFoundError(Exception):
    """Exception dilempar jika entitas tidak ditemukan di database."""
    pass


def jalankan_verifikasi(id_warga: int, id_program: int, id_petugas: int = None, catatan_awal: str = None) -> Verifikasi:
    """
    Fungsi inti evaluasi Rule Engine kelayakan bantuan sosial.
    Alur:
    1. Ambil data warga dan kriteria program.
    2. Cek apakah warga sudah pernah terdaftar (status layak/perlu_ditinjau) pada program yang sama
       -> jika ya, tolak proses dengan error.
    3. Jika ada field warga yang relevan tapi kosong/null -> status = 'perlu_ditinjau', catat field yang kurang.
    4. Jalankan pengecekan kriteria satu per satu, simpan hasil ke detail_pengecekan (dict/JSON):
       a. penghasilan warga <= batas_penghasilan_maks program?
       b. jumlah_tanggungan warga >= min_tanggungan program?
       c. kepemilikan_aset warga sesuai aset_maksimal_diizinkan program (jika ada batasan)?
    5. Evaluasi status_sistem:
       - Lolos semua -> 'layak'
       - Jelas gagal -> 'tidak_layak'
       - Ambiguitas/borderline -> 'perlu_ditinjau'
    6. Simpan record baru ke tabel verifikasi dengan status_sistem, status_final masih NULL.
    7. Catat ke file audit log dan kembalikan objek verifikasi.
    """
    # 1. Ambil data warga dan program
    warga = db.session.get(Warga, id_warga)
    if not warga:
        raise NotFoundError(f"Data warga dengan ID {id_warga} tidak ditemukan.")

    program = db.session.get(ProgramBantuan, id_program)
    if not program:
        raise NotFoundError(f"Program bantuan dengan ID {id_program} tidak ditemukan.")

    if not program.is_active:
        raise ValueError(f"Program bantuan '{program.nama_program}' sedang nonaktif.")

    # 3. Cek apakah warga sudah pernah terdaftar pada program yang sama (layak / perlu_ditinjau / exist)
    existing = Verifikasi.query.filter_by(id_warga=id_warga, id_program=id_program).first()
    if existing:
        current_status = existing.status_final or existing.status_otomatis
        if current_status in ["layak", "perlu_ditinjau"]:
            raise AlreadyVerifiedError(
                f"Pendaftaran ditolak: Warga '{warga.nama}' (NIK: {warga.nik}) sudah pernah terdaftar "
                f"pada program '{program.nama_program}' dengan status '{current_status}'. Duplikasi tidak diizinkan."
            )
        else:
            raise AlreadyVerifiedError(
                f"Pendaftaran ditolak: Riwayat verifikasi untuk warga '{warga.nama}' pada program '{program.nama_program}' "
                f"sudah ada dalam sistem (ID Verifikasi: {existing.id})."
            )

    # 2. Cek field warga yang relevan tapi kosong/null
    missing_fields = []
    if not warga.nama or not str(warga.nama).strip():
        missing_fields.append("nama")
    if not warga.alamat or not str(warga.alamat).strip():
        missing_fields.append("alamat")
    if warga.penghasilan is None:
        missing_fields.append("penghasilan")
    if warga.jumlah_tanggungan is None:
        missing_fields.append("jumlah_tanggungan")
    if warga.tanggal_lahir is None:
        missing_fields.append("tanggal_lahir")

    detail_pengecekan = {
        "kriteria_pengecekan": {},
        "field_kurang": missing_fields,
        "ringkasan": "",
        "rincian_aset": {
            "status_rumah": getattr(warga, "status_rumah_label", warga.status_rumah or "Milik Sendiri"),
            "luas_tanah": f"{warga.luas_tanah or 0} m²",
            "daya_listrik": getattr(warga, "daya_listrik_label", f"{warga.daya_listrik or 450} VA"),
            "jenis_kendaraan": getattr(warga, "jenis_kendaraan_label", warga.jenis_kendaraan or "Tidak Ada"),
            "jumlah_kendaraan": warga.jumlah_kendaraan or 0,
            "foto_kendaraan": warga.foto_kendaraan
        }
    }

    # Jika ada field relevan yang kosong -> langsung status 'perlu_ditinjau'
    if missing_fields:
        status_sistem = "perlu_ditinjau"
        ringkasan = f"Data profil warga tidak lengkap. Field yang kurang: {', '.join(missing_fields)}."
        detail_pengecekan["ringkasan"] = ringkasan
    else:
        # 4. Jalankan pengecekan kriteria satu per satu
        penghasilan_warga = Decimal(str(warga.penghasilan))
        batas_penghasilan = Decimal(str(program.kriteria_penghasilan_max))

        # a. Kriteria Penghasilan
        lolos_penghasilan = penghasilan_warga <= batas_penghasilan
        detail_pengecekan["kriteria_pengecekan"]["penghasilan"] = {
            "nilai": float(penghasilan_warga),
            "batas_maksimal": float(batas_penghasilan),
            "lolos": lolos_penghasilan
        }

        # b. Kriteria Tanggungan
        tanggungan_warga = int(warga.jumlah_tanggungan)
        min_tanggungan = int(program.kriteria_tanggungan_min)
        lolos_tanggungan = tanggungan_warga >= min_tanggungan
        detail_pengecekan["kriteria_pengecekan"]["tanggungan"] = {
            "nilai": tanggungan_warga,
            "batas_minimal": min_tanggungan,
            "lolos": lolos_tanggungan
        }

        # c. Kriteria Kepemilikan Aset (jika ada batasan)
        aset_warga = Decimal(str(warga.nilai_aset or 0.0))
        lolos_aset = True
        if program.kriteria_aset_max is not None:
            batas_aset = Decimal(str(program.kriteria_aset_max))
            lolos_aset = aset_warga <= batas_aset
            detail_pengecekan["kriteria_pengecekan"]["aset"] = {
                "nilai": float(aset_warga),
                "batas_maksimal": float(batas_aset),
                "lolos": lolos_aset
            }
        else:
            detail_pengecekan["kriteria_pengecekan"]["aset"] = {
                "nilai": float(aset_warga),
                "batas_maksimal": None,
                "lolos": True,
                "keterangan": "Tidak ada batasan aset maksimal pada program ini."
            }

        # d. Kriteria Desil Kesejahteraan
        desil_warga = warga.desil if warga.desil is not None else warga.hitung_desil_otomatis()
        lolos_desil = True
        if program.kriteria_desil_max is not None:
            max_desil = int(program.kriteria_desil_max)
            lolos_desil = desil_warga <= max_desil
            detail_pengecekan["kriteria_pengecekan"]["desil"] = {
                "nilai": desil_warga,
                "batas_maksimal": max_desil,
                "kategori_warga": warga.keterangan_desil["kategori"],
                "lolos": lolos_desil
            }
        else:
            detail_pengecekan["kriteria_pengecekan"]["desil"] = {
                "nilai": desil_warga,
                "batas_maksimal": None,
                "kategori_warga": warga.keterangan_desil["kategori"],
                "lolos": True,
                "keterangan": "Tidak ada batasan maksimal desil pada program ini."
            }

        # 5. Evaluasi status_sistem
        # Deteksi Anomali / Borderline: penghasilan Rp 0 atau nilai borderline
        is_borderline_anomali = (penghasilan_warga == Decimal("0"))

        if is_borderline_anomali:
            status_sistem = "perlu_ditinjau"
            ringkasan = "Penghasilan warga terdata Rp 0, memerlukan survei faktual lapangan untuk verifikasi keabsahan."
        elif lolos_penghasilan and lolos_tanggungan and lolos_aset and lolos_desil:
            status_sistem = "layak"
            ringkasan = f"Warga memenuhi seluruh kriteria kelayakan program bantuan (Termasuk Desil {desil_warga} - {warga.keterangan_desil['kategori']})."
        else:
            status_sistem = "tidak_layak"
            alasan_gagal = []
            if not lolos_penghasilan:
                alasan_gagal.append("penghasilan melebihi batas")
            if not lolos_tanggungan:
                alasan_gagal.append("jumlah tanggungan kurang dari batas minimal")
            if not lolos_aset:
                alasan_gagal.append("aset melebihi batas maksimal")
            if not lolos_desil:
                alasan_gagal.append(f"desil warga (Desil {desil_warga} - {warga.keterangan_desil['kategori']}) melebihi batas maksimal program (Maksimal Desil {program.kriteria_desil_max})")
            ringkasan = f"Tidak memenuhi kriteria: {', '.join(alasan_gagal)}."

        detail_pengecekan["ringkasan"] = ringkasan

    # 6. Simpan record baru ke tabel verifikasi dengan status_sistem, status_final masih NULL
    verifikasi_baru = Verifikasi(
        id_warga=id_warga,
        id_program=id_program,
        id_petugas=id_petugas if id_petugas else 1,
        status_otomatis=status_sistem,
        status_final=None,
        catatan_petugas=catatan_awal if catatan_awal else ringkasan,
        detail_pengecekan=detail_pengecekan,
        tanggal_verifikasi=datetime.datetime.now(),
        tanggal_konfirmasi=None
    )
    db.session.add(verifikasi_baru)
    db.session.commit()

    # Log aksi verifikasi untuk audit
    petugas_name = "System"
    if id_petugas:
        p = db.session.get(User, id_petugas)
        if p:
            petugas_name = f"{p.nama} ({p.username})"

    audit_logger.info(
        f"VERIFIKASI_BARU | VerifID: {verifikasi_baru.id} | Petugas: {petugas_name} | "
        f"Warga: {warga.nama} (NIK: {warga.nik}) | Program: {program.nama_program} | "
        f"Hasil_Sistem: {status_sistem.upper()} | Ringkasan: {ringkasan}"
    )

    return verifikasi_baru
