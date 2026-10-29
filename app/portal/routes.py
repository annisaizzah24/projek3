import os
import uuid
import datetime
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.portal import portal_bp
from app.auth.routes import role_required
from app.models import PengajuanKependudukan, Keluarga
from app.extensions import db
from app.forms import PengajuanKKForm, PengajuanWargaForm
from app.desil.routes import simpan_berkas_unggah


# =============================================================================
# HELPER: Simpan file upload ke folder uploads/pengajuan/
# =============================================================================
def _simpan_upload_pengajuan(file_obj, folder="pengajuan"):
    """Menyimpan file upload ke uploads/<folder>/, mengembalikan path relatif."""
    if not file_obj or not file_obj.filename:
        return None
    from werkzeug.utils import secure_filename
    ext = os.path.splitext(file_obj.filename)[1].lower()
    nama_file = f"{uuid.uuid4().hex}{ext}"
    upload_dir = os.path.join("uploads", folder)
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, nama_file)
    file_obj.save(path)
    return path


# =============================================================================
# 1. PORTAL — AJUKAN KK BARU: GET / POST /portal/ajukan-kk
# =============================================================================
@portal_bp.route("/ajukan-kk", methods=["GET", "POST"])
@login_required
@role_required("warga")
def ajukan_kk():
    """User mengajukan pendaftaran KK baru beserta data dirinya sebagai anggota."""
    form = PengajuanKKForm()

    if form.validate_on_submit():
        try:
            foto_rumah_path = _simpan_upload_pengajuan(form.foto_rumah.data, folder="pengajuan/rumah")
            foto_kendaraan_path = None
            if form.foto_kendaraan.data and form.foto_kendaraan.data.filename:
                foto_kendaraan_path = _simpan_upload_pengajuan(form.foto_kendaraan.data, folder="pengajuan/kendaraan")

            data_kk = {
                "nomor_kk": form.nomor_kk.data.strip(),
                "kepala_keluarga": form.kepala_keluarga.data.strip(),
                "alamat": form.alamat_kk.data.strip()
            }
            data_warga = {
                "nik": form.nik.data.strip(),
                "nama": form.nama.data.strip(),
                "tanggal_lahir": form.tanggal_lahir.data.isoformat(),
                "alamat": form.alamat.data.strip(),
                "penghasilan": str(form.penghasilan.data),
                "jumlah_tanggungan": form.jumlah_tanggungan.data or 0,
                "status_rumah": form.status_rumah.data,
                "luas_tanah": str(form.luas_tanah.data),
                "daya_listrik": form.daya_listrik.data,
                "jenis_kendaraan": form.jenis_kendaraan.data,
                "jumlah_kendaraan": form.jumlah_kendaraan.data or 0,
                "nilai_aset": None,   # akan dihitung otomatis saat admin approve
            }

            pengajuan = PengajuanKependudukan(
                id_user=current_user.id,
                jenis_pengajuan="kk_baru",
                status="menunggu",
                data_kk=data_kk,
                data_warga=data_warga,
                foto_rumah_path=foto_rumah_path,
                foto_kendaraan_path=foto_kendaraan_path,
            )
            db.session.add(pengajuan)
            db.session.commit()

            flash(
                "Pengajuan KK baru Anda telah berhasil dikirim dan sedang menunggu verifikasi Admin. "
                "Anda bisa memantau statusnya di halaman 'Status Pengajuan Saya'.",
                "success"
            )
            return redirect(url_for("portal.daftar_pengajuan_saya"))

        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal mengirim pengajuan: {str(exc)}", "danger")

    return render_template("portal/ajukan_kk.html", form=form)


# =============================================================================
# 2. PORTAL — AJUKAN ANGGOTA BARU: GET / POST /portal/ajukan-warga
# =============================================================================
@portal_bp.route("/ajukan-warga", methods=["GET", "POST"])
@login_required
@role_required("warga")
def ajukan_warga():
    """User mengajukan penambahan anggota warga ke KK yang sudah terdaftar."""
    form = PengajuanWargaForm()
    # Populate pilihan KK
    daftar_kk = Keluarga.query.order_by(Keluarga.nomor_kk.asc()).all()
    form.id_keluarga_target.choices = [
        (k.id, f"{k.nomor_kk} — {k.kepala_keluarga}")
        for k in daftar_kk
    ]

    if form.validate_on_submit():
        try:
            foto_rumah_path = _simpan_upload_pengajuan(form.foto_rumah.data, folder="pengajuan/rumah")
            foto_kendaraan_path = None
            if form.foto_kendaraan.data and form.foto_kendaraan.data.filename:
                foto_kendaraan_path = _simpan_upload_pengajuan(form.foto_kendaraan.data, folder="pengajuan/kendaraan")

            data_warga = {
                "nik": form.nik.data.strip(),
                "nama": form.nama.data.strip(),
                "tanggal_lahir": form.tanggal_lahir.data.isoformat(),
                "alamat": form.alamat.data.strip(),
                "penghasilan": str(form.penghasilan.data),
                "jumlah_tanggungan": form.jumlah_tanggungan.data or 0,
                "status_rumah": form.status_rumah.data,
                "luas_tanah": str(form.luas_tanah.data),
                "daya_listrik": form.daya_listrik.data,
                "jenis_kendaraan": form.jenis_kendaraan.data,
                "jumlah_kendaraan": form.jumlah_kendaraan.data or 0,
                "nilai_aset": None,
            }

            pengajuan = PengajuanKependudukan(
                id_user=current_user.id,
                jenis_pengajuan="warga_baru",
                status="menunggu",
                data_kk=None,
                data_warga=data_warga,
                id_keluarga_target=form.id_keluarga_target.data,
                foto_rumah_path=foto_rumah_path,
                foto_kendaraan_path=foto_kendaraan_path,
            )
            db.session.add(pengajuan)
            db.session.commit()

            flash(
                "Pengajuan anggota warga baru Anda telah berhasil dikirim dan sedang menunggu verifikasi Admin. "
                "Anda bisa memantau statusnya di halaman 'Status Pengajuan Saya'.",
                "success"
            )
            return redirect(url_for("portal.daftar_pengajuan_saya"))

        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal mengirim pengajuan: {str(exc)}", "danger")

    return render_template("portal/ajukan_warga.html", form=form, daftar_kk=daftar_kk)


# =============================================================================
# 3. PORTAL — STATUS PENGAJUAN SAYA: GET /portal/pengajuan
# =============================================================================
@portal_bp.route("/pengajuan", methods=["GET"])
@login_required
@role_required("warga")
def daftar_pengajuan_saya():
    """Menampilkan riwayat dan status pengajuan kependudukan milik user yang sedang login."""
    # SECURITY: hanya query milik current_user — tidak bisa melihat data user lain
    pengajuan_list = (
        PengajuanKependudukan.query
        .filter_by(id_user=current_user.id)
        .order_by(PengajuanKependudukan.tanggal_pengajuan.desc())
        .all()
    )
    return render_template("portal/daftar_pengajuan.html", pengajuan_list=pengajuan_list)
