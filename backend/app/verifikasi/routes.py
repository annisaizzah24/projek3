import datetime
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app.verifikasi import verifikasi_bp
from app.verifikasi.engine import jalankan_verifikasi, AlreadyVerifiedError, NotFoundError, audit_logger
from app.models import Verifikasi, Warga, ProgramBantuan, User
from app.extensions import db
from app.forms import MulaiVerifikasiForm, KonfirmasiForm
from app.auth.routes import role_required


@verifikasi_bp.route("", methods=["GET"])
@login_required
@role_required("admin", "petugas_verifikasi")
def index():
    """Redirect default /verifikasi ke halaman riwayat."""
    return redirect(url_for("verifikasi.riwayat_verifikasi"))


# =============================================================================
# 1. GET / POST /verifikasi/mulai & /verifikasi/proses: Form Mulai Verifikasi
# =============================================================================
@verifikasi_bp.route("/mulai", methods=["GET", "POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def mulai_verifikasi():
    form = MulaiVerifikasiForm()

    # Pre-select warga from query parameter if available on GET (misal dari tabel warga ?id_warga=1)
    if request.method == "GET" and request.args.get("id_warga"):
        try:
            form.id_warga.data = int(request.args.get("id_warga"))
        except (ValueError, TypeError):
            pass

    if form.validate_on_submit():
        id_warga = form.id_warga.data
        id_program = form.id_program.data
        catatan_awal = (form.catatan.data or "").strip()

        try:
            verifikasi_baru = jalankan_verifikasi(
                id_warga=id_warga,
                id_program=id_program,
                id_petugas=current_user.id,
                catatan_awal=catatan_awal
            )
            flash(
                f"Evaluasi selesai. Hasil Rule Engine: [{verifikasi_baru.status_otomatis.upper()}]. "
                f"Silakan tinjau rincian audit kriteria dan tetapkan konfirmasi akhir.",
                "success"
            )
            return redirect(url_for("verifikasi.detail_verifikasi", id=verifikasi_baru.id))

        except AlreadyVerifiedError as ave:
            flash(str(ave), "warning")
            existing = Verifikasi.query.filter_by(id_warga=id_warga, id_program=id_program).first()
            if existing:
                return redirect(url_for("verifikasi.detail_verifikasi", id=existing.id))
            form.id_warga.errors.append(str(ave))

        except NotFoundError as nfe:
            flash(str(nfe), "danger")

        except IntegrityError:
            db.session.rollback()
            form.id_warga.errors.append("Warga sudah terdaftar pada program bantuan tersebut.")
            flash("Terjadi pelanggaran integritas data: Warga sudah terdaftar pada program bantuan tersebut.", "danger")

        except Exception as exc:
            db.session.rollback()
            flash(f"Terjadi kesalahan saat memproses verifikasi: {str(exc)}", "danger")

    return render_template("verifikasi/form_verifikasi.html", form=form)


@verifikasi_bp.route("/proses", methods=["POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def proses_verifikasi():
    """Alias endpoint POST /proses ke mulai_verifikasi."""
    return mulai_verifikasi()


# =============================================================================
# 2. POST /verifikasi/<id>/konfirmasi: Konfirmasi Final Petugas (HANYA BISA SEKALI)
# =============================================================================
@verifikasi_bp.route("/<int:id>/konfirmasi", methods=["POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def konfirmasi_verifikasi(id):
    verif = db.get_or_404(Verifikasi, id)

    # Validasi: Hanya bisa dilakukan sekali (tolak jika tanggal_konfirmasi sudah terisi)
    if verif.tanggal_konfirmasi is not None:
        flash(
            f"Gagal: Verifikasi ID #{verif.id} sudah pernah dikonfirmasi pada "
            f"{verif.tanggal_konfirmasi.strftime('%d-%m-%Y %H:%M')} dan tidak dapat diubah kembali demi menjaga integritas data audit.",
            "danger"
        )
        return redirect(url_for("verifikasi.detail_verifikasi", id=verif.id))

    form = KonfirmasiForm()

    if form.validate_on_submit():
        status_final = form.status_final.data.strip()
        catatan_petugas = form.catatan_petugas.data.strip()

        try:
            verif.status_final = status_final
            verif.catatan_petugas = catatan_petugas
            verif.tanggal_konfirmasi = datetime.datetime.now()
            verif.id_petugas = current_user.id
            db.session.commit()

            # Audit log konfirmasi
            audit_logger.info(
                f"KONFIRMASI_PETUGAS | VerifID: {verif.id} | Petugas: {current_user.nama} ({current_user.username}) | "
                f"Warga: {verif.warga.nama} | Status_Final: {status_final.upper()} | Catatan: {verif.catatan_petugas}"
            )

            flash(f"Status verifikasi telah berhasil dikonfirmasi secara final menjadi [{status_final.upper()}].", "success")
            return redirect(url_for("verifikasi.detail_verifikasi", id=verif.id))
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal menyimpan konfirmasi verifikasi: {str(exc)}", "danger")

    return render_template("verifikasi/detail.html", verif=verif, form=form)


# =============================================================================
# 3. GET /verifikasi/riwayat: Daftar Semua Verifikasi dengan Filter Status, Program, Tanggal
# =============================================================================
@verifikasi_bp.route("/riwayat", methods=["GET"])
@login_required
@role_required("admin", "petugas_verifikasi")
def riwayat_verifikasi():
    status_filter = request.args.get("status", "").strip()
    program_id = request.args.get("program_id", type=int)
    tgl_mulai_str = request.args.get("tanggal_mulai", "").strip()
    tgl_selesai_str = request.args.get("tanggal_selesai", "").strip()

    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(100, request.args.get("per_page", 10, type=int)))

    query = Verifikasi.query.join(Warga).join(ProgramBantuan)

    # Filter status (baik otomatis maupun final)
    if status_filter in ["layak", "tidak_layak", "perlu_ditinjau"]:
        query = query.filter(
            db.or_(
                Verifikasi.status_final == status_filter,
                db.and_(Verifikasi.status_final == None, Verifikasi.status_otomatis == status_filter)
            )
        )
    elif status_filter == "pending":
        query = query.filter(Verifikasi.status_final == None)

    # Filter Program
    if program_id:
        query = query.filter(Verifikasi.id_program == program_id)

    # Filter Rentang Tanggal
    if tgl_mulai_str:
        try:
            tgl_mulai = datetime.datetime.strptime(tgl_mulai_str, "%Y-%m-%d")
            query = query.filter(Verifikasi.tanggal_verifikasi >= tgl_mulai)
        except ValueError:
            pass

    if tgl_selesai_str:
        try:
            tgl_selesai = datetime.datetime.strptime(tgl_selesai_str, "%Y-%m-%d") + datetime.timedelta(days=1)
            query = query.filter(Verifikasi.tanggal_verifikasi < tgl_selesai)
        except ValueError:
            pass

    pagination = query.order_by(Verifikasi.tanggal_verifikasi.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    daftar_program = ProgramBantuan.query.order_by(ProgramBantuan.nama_program.asc()).all()

    return render_template(
        "verifikasi/index.html",
        pagination=pagination,
        daftar_program=daftar_program,
        selected_status=status_filter,
        selected_program=program_id,
        tanggal_mulai=tgl_mulai_str,
        tanggal_selesai=tgl_selesai_str
    )


# =============================================================================
# 4. GET /verifikasi/<id>: Detail Satu Verifikasi Termasuk Breakdown Kriteria
# =============================================================================
@verifikasi_bp.route("/<int:id>", methods=["GET"])
@login_required
def detail_verifikasi(id):
    verif = db.get_or_404(Verifikasi, id)

    # Batasi hak akses warga agar hanya dapat melihat data verifikasinya sendiri
    if current_user.is_warga:
        if not current_user.data_warga or verif.id_warga != current_user.data_warga.id:
            flash("Akses ditolak: Anda hanya berhak melihat rincian verifikasi Anda sendiri.", "danger")
            abort(403)

    form = KonfirmasiForm()
    if verif.tanggal_konfirmasi:
        form.status_final.data = verif.status_final
        form.catatan_petugas.data = verif.catatan_petugas
    else:
        # Pre-select status_final with status_otomatis to assist the officer
        form.status_final.data = verif.status_otomatis

    return render_template("verifikasi/detail.html", verif=verif, form=form)
