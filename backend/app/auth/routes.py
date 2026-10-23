from urllib.parse import urlsplit
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from app.auth import auth_bp
from app.models import User
from app.extensions import db
from app.forms import LoginForm, PetugasForm, EditPetugasForm, RegisterForm


def role_required(*roles):
    """
    Decorator custom untuk membatasi akses endpoint berdasarkan role pengguna.
    Contoh:
        @role_required('admin')
        @role_required('admin', 'petugas_verifikasi')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Silakan login terlebih dahulu untuk mengakses halaman ini.", "warning")
                return redirect(url_for("auth.login", next=request.url))
            if current_user.role not in roles:
                flash("Akses ditolak: Anda tidak memiliki izin untuk halaman ini.", "danger")
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/registrasi", methods=["GET", "POST"])
def register():
    """Halaman dan proses pendaftaran mandiri akun warga/user baru."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            nik_val = form.nik.data.strip() if form.nik.data else None
            user_baru = User(
                username=form.username.data.strip(),
                nama=form.nama.data.strip(),
                role="warga",
                nik=nik_val
            )
            user_baru.set_password(form.password.data)
            db.session.add(user_baru)
            db.session.commit()

            flash(
                f"Pendaftaran berhasil! Akun warga atas nama '{user_baru.nama}' telah aktif. "
                "Silakan masuk ke sistem menggunakan username dan password Anda.",
                "success"
            )
            return redirect(url_for("auth.login"))
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("Username sudah terdaftar dalam sistem, silakan pilih username lain.")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal melakukan pendaftaran: {str(exc)}", "danger")

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash(f"Selamat datang kembali, {user.nama} ({user.role})!", "success")
            next_page = request.args.get("next")
            # Validasi URL internal agar terhindar dari Open Redirect
            if not next_page or urlsplit(next_page).netloc != "" or not next_page.startswith("/"):
                next_page = url_for("dashboard")
            return redirect(next_page)
        else:
            form.password.errors.append("Username atau password salah. Silakan periksa kembali.")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Anda telah berhasil logout.", "info")
    return redirect(url_for("auth.login"))


# =============================================================================
# KHUSUS ADMIN: KELOLA PETUGAS & ADMINISTRATOR
# =============================================================================
@auth_bp.route("/petugas", methods=["GET"])
@login_required
@role_required("admin")
def daftar_petugas():
    # Filter khusus role ADMINISTRATOR dan PETUGAS VERIFIKASI (akun warga tidak boleh muncul)
    daftar_user = User.query.filter(
        User.role.in_(["admin", "petugas_verifikasi"])
    ).order_by(User.id.asc()).all()
    return render_template("auth/petugas.html", daftar_user=daftar_user)


@auth_bp.route("/petugas/tambah", methods=["GET", "POST"])
@login_required
@role_required("admin")
def tambah_petugas():
    form = PetugasForm()
    if form.validate_on_submit():
        if form.role.data not in ["admin", "petugas_verifikasi"]:
            flash("Role tidak valid. Hanya peran Administrator atau Petugas Verifikasi yang dapat didaftarkan.", "danger")
            return render_template("auth/form_petugas.html", form=form)
        try:
            user_baru = User(
                username=form.username.data.strip(),
                nama=form.nama.data.strip(),
                role=form.role.data
            )
            user_baru.set_password(form.password.data)
            db.session.add(user_baru)
            db.session.commit()
            role_label = "Administrator" if user_baru.role == "admin" else "Petugas Verifikasi"
            flash(f"Pengguna baru '{user_baru.nama}' ({role_label}) berhasil didaftarkan.", "success")
            return redirect(url_for("auth.daftar_petugas"))
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("Username sudah terdaftar dalam sistem.")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal menambahkan pengguna: {str(exc)}", "danger")

    return render_template("auth/form_petugas.html", form=form)


@auth_bp.route("/petugas/<int:id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_petugas(id):
    """Pengubahan data akun petugas atau admin oleh Administrator."""
    user = User.query.get_or_404(id)
    if user.role not in ["admin", "petugas_verifikasi"]:
        flash("Akses ditolak: Hanya akun Administrator atau Petugas Verifikasi yang dapat dikelola di sini.", "danger")
        return redirect(url_for("auth.daftar_petugas"))

    form = EditPetugasForm(current_user_id=user.id, obj=user)

    if form.validate_on_submit():
        new_role = form.role.data
        if new_role not in ["admin", "petugas_verifikasi"]:
            flash("Role yang dipilih tidak valid.", "danger")
            return render_template("auth/form_petugas.html", form=form, is_edit=True, user=user)

        # Cegah administrator mengubah rolenya sendiri menjadi non-admin
        if current_user.id == user.id and new_role != "admin":
            flash("Anda tidak dapat mencabut hak akses Administrator dari akun Anda sendiri.", "danger")
            return redirect(url_for("auth.daftar_petugas"))

        try:
            user.nama = form.nama.data.strip()
            user.username = form.username.data.strip()
            user.role = new_role
            if form.password.data and form.password.data.strip():
                user.set_password(form.password.data.strip())

            db.session.commit()
            flash(f"Data akun '{user.nama}' berhasil diperbarui.", "success")
            return redirect(url_for("auth.daftar_petugas"))
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("Username sudah terdaftar dalam sistem.")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal memperbarui akun: {str(exc)}", "danger")

    return render_template("auth/form_petugas.html", form=form, is_edit=True, user=user)


@auth_bp.route("/petugas/<int:id>/hapus", methods=["POST"])
@login_required
@role_required("admin")
def hapus_petugas(id):
    if current_user.id == id:
        flash("Anda tidak dapat menghapus akun Anda sendiri.", "danger")
        return redirect(url_for("auth.daftar_petugas"))

    user = User.query.get_or_404(id)
    if user.role not in ["admin", "petugas_verifikasi"]:
        flash("Akses ditolak: Hanya akun Administrator atau Petugas Verifikasi yang dapat dikelola di halaman ini.", "danger")
        return redirect(url_for("auth.daftar_petugas"))

    try:
        nama = user.nama
        db.session.delete(user)
        db.session.commit()
        flash(f"Akun pengguna '{nama}' berhasil dihapus.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Gagal menghapus pengguna: {str(exc)}", "danger")

    return redirect(url_for("auth.daftar_petugas"))


@auth_bp.route("/akun-warga", methods=["GET"])
@auth_bp.route("/users/warga", methods=["GET"])
@login_required
@role_required("admin", "petugas_verifikasi")
def daftar_akun_warga():
    """Endpoint query terpisah khusus untuk mengambil daftar akun dengan role WARGA."""
    daftar_warga_user = User.query.filter_by(role="warga").order_by(User.id.asc()).all()
    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        return jsonify({
            "success": True,
            "total": len(daftar_warga_user),
            "users": [
                {"id": u.id, "username": u.username, "nama": u.nama, "role": u.role, "nik": u.nik}
                for u in daftar_warga_user
            ]
        })
    return render_template("auth/warga_users.html", daftar_warga=daftar_warga_user)

