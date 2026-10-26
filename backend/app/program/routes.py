from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.exc import IntegrityError
from app.program import program_bp
from app.models import ProgramBantuan, Verifikasi, DESIL_INFO
from app.extensions import db
from app.forms import ProgramForm
from app.auth.routes import role_required


@program_bp.route("", methods=["GET"])
@login_required
def daftar_program():
    programs = ProgramBantuan.query.order_by(ProgramBantuan.id.asc()).all()
    return render_template("program/index.html", programs=programs, desil_info=DESIL_INFO)


@program_bp.route("/tambah", methods=["GET", "POST"])
@login_required
@role_required("admin")
def tambah_program():
    form = ProgramForm()

    if form.validate_on_submit():
        try:
            desil_max = form.kriteria_desil_max.data if (form.kriteria_desil_max.data and form.kriteria_desil_max.data > 0) else None
            program_baru = ProgramBantuan(
                nama_program=form.nama_program.data.strip(),
                kriteria_penghasilan_max=form.kriteria_penghasilan_max.data,
                kriteria_tanggungan_min=form.kriteria_tanggungan_min.data if form.kriteria_tanggungan_min.data is not None else 0,
                kriteria_aset_max=form.kriteria_aset_max.data,
                kriteria_desil_max=desil_max,
                deskripsi=form.deskripsi.data.strip() if form.deskripsi.data else None,
                is_active=True
            )
            db.session.add(program_baru)
            db.session.commit()
            flash(f"Program Bantuan '{program_baru.nama_program}' berhasil ditambahkan.", "success")
            return redirect(url_for("program.daftar_program"))
        except IntegrityError:
            db.session.rollback()
            flash("Terjadi kesalahan integritas database saat menyimpan program bantuan.", "danger")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal menambahkan program: {str(exc)}", "danger")

    return render_template("program/form_program.html", form=form, is_edit=False)


@program_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_program(id):
    program = db.get_or_404(ProgramBantuan, id)
    form = ProgramForm(obj=program)

    if request.method == "GET":
        form.kriteria_desil_max.data = program.kriteria_desil_max or 0

    if form.validate_on_submit():
        try:
            desil_max = form.kriteria_desil_max.data if (form.kriteria_desil_max.data and form.kriteria_desil_max.data > 0) else None
            program.nama_program = form.nama_program.data.strip()
            program.kriteria_penghasilan_max = form.kriteria_penghasilan_max.data
            program.kriteria_tanggungan_min = form.kriteria_tanggungan_min.data if form.kriteria_tanggungan_min.data is not None else 0
            program.kriteria_aset_max = form.kriteria_aset_max.data
            program.kriteria_desil_max = desil_max
            program.deskripsi = form.deskripsi.data.strip() if form.deskripsi.data else None

            db.session.commit()
            flash(f"Program '{program.nama_program}' berhasil diperbarui.", "success")
            return redirect(url_for("program.daftar_program"))
        except IntegrityError:
            db.session.rollback()
            flash("Terjadi kesalahan integritas database saat memperbarui program.", "danger")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal memperbarui program: {str(exc)}", "danger")

    return render_template("program/form_program.html", form=form, program=program, is_edit=True)


@program_bp.route("/<int:id>/nonaktifkan", methods=["POST"])
@login_required
@role_required("admin")
def nonaktifkan_program(id):
    """Mengubah status aktif/nonaktif program bantuan (hanya admin)."""
    program = db.get_or_404(ProgramBantuan, id)
    try:
        program.is_active = not program.is_active
        db.session.commit()
        status_str = "diaktifkan kembali" if program.is_active else "dinonaktifkan"
        flash(f"Program '{program.nama_program}' berhasil {status_str}.", "info")
    except Exception as exc:
        db.session.rollback()
        flash(f"Gagal mengubah status program: {str(exc)}", "danger")

    return redirect(url_for("program.daftar_program"))


@program_bp.route("/<int:id>/hapus", methods=["POST"])
@login_required
@role_required("admin")
def hapus_program(id):
    program = db.get_or_404(ProgramBantuan, id)

    verif_count = Verifikasi.query.filter_by(id_program=program.id).count()
    if verif_count > 0:
        flash(
            f"Program '{program.nama_program}' tidak dapat dihapus karena telah memiliki {verif_count} data historis verifikasi.",
            "danger"
        )
        return redirect(url_for("program.daftar_program"))

    try:
        nama = program.nama_program
        db.session.delete(program)
        db.session.commit()
        flash(f"Program '{nama}' berhasil dihapus dari sistem.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Gagal menghapus program: {str(exc)}", "danger")

    return redirect(url_for("program.daftar_program"))

import os
from flask import request, jsonify
from werkzeug.utils import secure_filename
from app.ocr_kk import baca_kk

UPLOAD_DIR = "uploads/temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@bp.route("/keluarga/ocr", methods=["POST"])
def ocr_kk_route():
    file = request.files.get("foto_kk")
    if not file or not file.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        return jsonify({"error": "File harus berupa gambar JPG/PNG"}), 400

    path = os.path.join(UPLOAD_DIR, secure_filename(file.filename))
    file.save(path)
    try:
        return jsonify(baca_kk(path))
    finally:
        os.remove(path)