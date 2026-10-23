import os
import uuid
import datetime
from decimal import Decimal
from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import Warga, PengajuanDesil, User, ProgramBantuan, DESIL_INFO, get_desil_info
from app.forms import PengajuanPerubahanDesilForm, ReviewPengajuanDesilForm
from app.auth.routes import role_required
from app.desil import desil_bp


def simpan_berkas_unggah(file_storage, folder="rumah"):
    """
    Menyimpan berkas unggahan ke folder static/uploads/<folder>
    dengan nama acak unik dan aman.
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        return None

    static_folder = current_app.static_folder or os.path.join(current_app.root_path, "static")
    target_dir = os.path.join(static_folder, "uploads", folder)
    os.makedirs(target_dir, exist_ok=True)

    orig_filename = secure_filename(file_storage.filename)
    ext = os.path.splitext(orig_filename)[1].lower() or ".jpg"
    unique_name = f"{folder}_{uuid.uuid4().hex[:10]}_{int(datetime.datetime.now().timestamp())}{ext}"
    dest_path = os.path.join(target_dir, unique_name)
    file_storage.save(dest_path)
    return f"uploads/{folder}/{unique_name}"


# =============================================================================
# 1. AJUKAN PERUBAHAN DESIL (UNTUK WARGA)
# GET / POST /pengajuan-desil/ajukan
# =============================================================================
@desil_bp.route("/pengajuan-desil/ajukan", methods=["GET", "POST"])
@login_required
def ajukan_perubahan():
    """
    Formulir bagi warga untuk mengajukan sanggahan / perubahan kategori desil.
    Misalnya jika sistem mencatat Desil 7 atau 10, padahal kondisi riil tergolong miskin.
    """
    # Warga dapat mengajukan untuk dirinya sendiri, atau petugas dapat membantu inputkan
    warga = None
    if current_user.is_warga:
        warga = current_user.data_warga
        if not warga:
            flash(
                "Profil data kependudukan (NIK) Anda belum terhubung dengan master data warga kelurahan. "
                "Silakan hubungi petugas kelurahan untuk verifikasi data NIK.",
                "warning"
            )
            return redirect(url_for("dashboard"))
    else:
        # Jika dibuka oleh admin / petugas, cek apakah ada parameter warga_id
        warga_id = request.args.get("warga_id", type=int)
        if warga_id:
            warga = db.session.get(Warga, warga_id)
        if not warga:
            flash("Pilih data warga terlebih dahulu untuk membuat pengajuan perubahan desil.", "info")
            return redirect(url_for("warga.daftar_warga"))

    # Cek apakah sudah ada pengajuan yang berstatus 'menunggu'
    pengajuan_aktif = PengajuanDesil.query.filter_by(id_warga=warga.id, status="menunggu").first()
    if pengajuan_aktif:
        flash(
            f"Warga '{warga.nama}' telah memiliki pengajuan perubahan desil yang berstatus Menunggu Verifikasi "
            f"(Diajukan pada {pengajuan_aktif.tanggal_pengajuan.strftime('%d/%m/%Y')}). Harap menunggu hasil verifikasi petugas.",
            "warning"
        )
        if current_user.is_warga:
            return redirect(url_for("desil.riwayat_saya"))
        else:
            return redirect(url_for("desil.detail_pengajuan", id=pengajuan_aktif.id))

    form = PengajuanPerubahanDesilForm()

    if form.validate_on_submit():
        try:
            # Unggah foto rumah baru
            foto_rumah_path = simpan_berkas_unggah(form.foto_rumah.data, folder="rumah")
            if not foto_rumah_path:
                flash("Foto rumah wajib diunggah.", "danger")
                return render_template("desil/ajukan.html", form=form, warga=warga)

            # Unggah dokumen pendukung opsional
            dok_path = None
            if form.dokumen_pendukung.data:
                dok_path = simpan_berkas_unggah(form.dokumen_pendukung.data, folder="dokumen")

            desil_saat_ini = warga.desil if warga.desil is not None else warga.hitung_desil_otomatis()

            pengajuan_baru = PengajuanDesil(
                id_warga=warga.id,
                id_user=current_user.id,
                desil_lama=desil_saat_ini,
                desil_diajukan=form.desil_diajukan.data,
                penghasilan_terkini=form.penghasilan_terkini.data,
                jumlah_tanggungan=form.jumlah_tanggungan.data or 0,
                foto_rumah_baru=foto_rumah_path,
                dokumen_pendukung=dok_path,
                alasan_pengajuan=form.alasan_pengajuan.data.strip(),
                status="menunggu"
            )

            db.session.add(pengajuan_baru)
            db.session.commit()

            flash(
                f"Permohonan perubahan desil berhasil diajukan! Bukti foto rumah dan penghasilan terbaru "
                f"akan segera diverifikasi oleh petugas kelurahan.",
                "success"
            )
            if current_user.is_warga:
                return redirect(url_for("desil.riwayat_saya"))
            else:
                return redirect(url_for("desil.daftar_pengajuan"))

        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal mengirimkan pengajuan: {str(exc)}", "danger")

    return render_template(
        "desil/ajukan.html",
        form=form,
        warga=warga,
        desil_info=DESIL_INFO
    )


# =============================================================================
# 2. RIWAYAT PENGAJUAN SAYA (UNTUK WARGA)
# GET /pengajuan-desil/saya
# =============================================================================
@desil_bp.route("/pengajuan-desil/saya", methods=["GET"])
@login_required
def riwayat_saya():
    """Menampilkan riwayat seluruh pengajuan perubahan desil milik akun warga."""
    warga = current_user.data_warga
    daftar_pengajuan = []
    if warga:
        daftar_pengajuan = PengajuanDesil.query.filter_by(id_warga=warga.id).order_by(
            PengajuanDesil.tanggal_pengajuan.desc()
        ).all()
    elif current_user.is_warga:
        daftar_pengajuan = PengajuanDesil.query.filter_by(id_user=current_user.id).order_by(
            PengajuanDesil.tanggal_pengajuan.desc()
        ).all()

    return render_template(
        "desil/riwayat_warga.html",
        daftar_pengajuan=daftar_pengajuan,
        warga=warga,
        desil_info=DESIL_INFO
    )


# =============================================================================
# 3. DAFTAR SELURUH PENGAJUAN (UNTUK PETUGAS & ADMIN)
# GET /pengajuan-desil
# =============================================================================
@desil_bp.route("/pengajuan-desil", methods=["GET"])
@login_required
@role_required("admin", "petugas_verifikasi")
def daftar_pengajuan():
    """Daftar permohonan perubahan desil yang masuk dari warga."""
    status_filter = request.args.get("status", "").strip().lower()
    search = request.args.get("search", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(50, request.args.get("per_page", 10, type=int)))

    query = PengajuanDesil.query.join(Warga, PengajuanDesil.id_warga == Warga.id)

    if status_filter in ["menunggu", "disetujui", "ditolak"]:
        query = query.filter(PengajuanDesil.status == status_filter)

    if search:
        wildcard = f"%{search}%"
        query = query.filter(
            db.or_(
                Warga.nama.ilike(wildcard),
                Warga.nik.ilike(wildcard)
            )
        )

    pagination = query.order_by(
        # Prioritas: yang 'menunggu' ditaruh di paling atas
        db.case((PengajuanDesil.status == "menunggu", 1), else_=2),
        PengajuanDesil.tanggal_pengajuan.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    total_menunggu = PengajuanDesil.query.filter_by(status="menunggu").count()
    total_disetujui = PengajuanDesil.query.filter_by(status="disetujui").count()
    total_ditolak = PengajuanDesil.query.filter_by(status="ditolak").count()

    return render_template(
        "desil/index.html",
        pagination=pagination,
        status_filter=status_filter,
        search=search,
        total_menunggu=total_menunggu,
        total_disetujui=total_disetujui,
        total_ditolak=total_ditolak,
        desil_info=DESIL_INFO
    )


# =============================================================================
# 4. DETAIL & VERIFIKASI PENGAJUAN
# GET / POST /pengajuan-desil/<id>
# =============================================================================
@desil_bp.route("/pengajuan-desil/<int:id>", methods=["GET", "POST"])
@login_required
def detail_pengajuan(id):
    """
    Rincian permohonan perubahan desil:
    - Menampilkan perbandingan data lama vs data riil yang diajukan
    - Menampilkan foto fisik rumah lama dan baru
    - Petugas dapat menyetujui (memperbarui profil warga) atau menolak
    """
    pengajuan = db.get_or_404(PengajuanDesil, id)

    # Batasi warga hanya bisa melihat miliknya sendiri
    if current_user.is_warga:
        if pengajuan.id_user != current_user.id and (not current_user.data_warga or pengajuan.id_warga != current_user.data_warga.id):
            abort(403)
        if request.method == "POST":
            flash("Akses ditolak: Warga tidak memiliki hak untuk memverifikasi atau menyetujui pengajuan desil.", "danger")
            abort(403)

    form = ReviewPengajuanDesilForm()

    if request.method == "GET":
        form.desil_disetujui.data = pengajuan.desil_diajukan
        form.status.data = pengajuan.status if pengajuan.status != "menunggu" else "disetujui"
        form.catatan_petugas.data = pengajuan.catatan_petugas or ""

    if form.validate_on_submit() and not current_user.is_warga:
        try:
            status_keputusan = form.status.data
            desil_final = form.desil_disetujui.data
            catatan = form.catatan_petugas.data.strip()

            pengajuan.status = status_keputusan
            pengajuan.catatan_petugas = catatan
            pengajuan.id_petugas = current_user.id
            pengajuan.tanggal_verifikasi = datetime.datetime.now()

            warga = pengajuan.warga

            if status_keputusan == "disetujui":
                # Terapkan perubahan ke profil data Warga
                warga.desil = desil_final
                warga.penghasilan = pengajuan.penghasilan_terkini
                warga.foto_rumah = pengajuan.foto_rumah_baru
                if pengajuan.jumlah_tanggungan is not None:
                    warga.jumlah_tanggungan = pengajuan.jumlah_tanggungan

                db.session.commit()
                info_desil_baru = get_desil_info(desil_final)
                flash(
                    f"Pengajuan disetujui! Data warga '{warga.nama}' berhasil diperbarui ke Desil {desil_final} "
                    f"({info_desil_baru['kategori']}). Warga kini memenuhi syarat untuk verifikasi bantuan sosial.",
                    "success"
                )
            else:
                db.session.commit()
                flash(f"Pengajuan perubahan desil warga '{warga.nama}' ditolak.", "warning")

            return redirect(url_for("desil.detail_pengajuan", id=pengajuan.id))

        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal memperbarui status pengajuan: {str(exc)}", "danger")

    return render_template(
        "desil/detail.html",
        pengajuan=pengajuan,
        form=form,
        desil_info=DESIL_INFO
    )


# =============================================================================
# 5. HAPUS PENGAJUAN (ADMIN ONLY)
# POST /pengajuan-desil/<id>/hapus
# =============================================================================
@desil_bp.route("/pengajuan-desil/<int:id>/hapus", methods=["POST"])
@login_required
@role_required("admin")
def hapus_pengajuan(id):
    """Menghapus data permohonan pengajuan desil."""
    pengajuan = db.get_or_404(PengajuanDesil, id)
    try:
        db.session.delete(pengajuan)
        db.session.commit()
        flash("Data pengajuan perubahan desil berhasil dihapus.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Gagal menghapus pengajuan: {str(exc)}", "danger")

    return redirect(url_for("desil.daftar_pengajuan"))
