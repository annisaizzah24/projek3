import os
from flask import Flask, redirect, url_for, render_template
from flask_login import login_required, current_user
from config import config_by_name
from app.extensions import db, login_manager, migrate


def create_app(config_name="default"):
    """Application factory for Sociovault."""
    # Resolusi path dinamis ke folder frontend/
    curr_dir = os.path.abspath(os.path.dirname(__file__))
    parent_dir = os.path.abspath(os.path.join(curr_dir, ".."))
    proj_root = os.path.abspath(os.path.join(curr_dir, "..", "..")) if os.path.basename(parent_dir) == "backend" else parent_dir

    frontend_dir = os.path.join(proj_root, "frontend")
    template_dir = os.path.join(frontend_dir, "templates")
    static_dir = os.path.join(frontend_dir, "static")

    if not os.path.exists(template_dir):
        template_dir = os.path.join(curr_dir, "templates")
        static_dir = os.path.join(curr_dir, "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )
    app.config.from_object(config_by_name[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Register Blueprints
    from app.auth import auth_bp
    from app.warga import warga_bp
    from app.program import program_bp
    from app.verifikasi import verifikasi_bp
    from app.desil import desil_bp
    from app.portal import portal_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(warga_bp)
    app.register_blueprint(program_bp)
    app.register_blueprint(verifikasi_bp)
    app.register_blueprint(desil_bp)
    app.register_blueprint(portal_bp)

    # Context Processor untuk variabel global template
    @app.context_processor
    def inject_globals():
        from app.models import PengajuanDesil, PengajuanKependudukan, DESIL_INFO, get_desil_info
        pending_desil = 0
        pending_kependudukan = 0
        if current_user.is_authenticated and not current_user.is_warga:
            try:
                pending_desil = PengajuanDesil.query.filter_by(status="menunggu").count()
            except Exception:
                pending_desil = 0
            try:
                pending_kependudukan = PengajuanKependudukan.query.filter_by(status="menunggu").count()
            except Exception:
                pending_kependudukan = 0
        return {
            "pending_desil_count": pending_desil,
            "pending_kependudukan_count": pending_kependudukan,
            "DESIL_INFO": DESIL_INFO,
            "get_desil_info": get_desil_info
        }

    # Root route redirect
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    # Dashboard route
    @app.route("/dashboard")
    @login_required
    def dashboard():
        from app.models import Warga, Keluarga, ProgramBantuan, Verifikasi, PengajuanDesil

        # Tampilan khusus jika pengguna login dengan role 'warga'
        if current_user.is_warga:
            warga_terkait = current_user.data_warga
            daftar_program = ProgramBantuan.query.filter_by(is_active=True).all()
            riwayat_user = []
            riwayat_desil = []
            if warga_terkait:
                riwayat_user = Verifikasi.query.filter_by(id_warga=warga_terkait.id).order_by(Verifikasi.tanggal_verifikasi.desc()).all()
                riwayat_desil = PengajuanDesil.query.filter_by(id_warga=warga_terkait.id).order_by(PengajuanDesil.tanggal_pengajuan.desc()).all()
            else:
                riwayat_desil = PengajuanDesil.query.filter_by(id_user=current_user.id).order_by(PengajuanDesil.tanggal_pengajuan.desc()).all()

            return render_template(
                "dashboard_warga.html",
                warga=warga_terkait,
                daftar_program=daftar_program,
                riwayat=riwayat_user,
                riwayat_desil=riwayat_desil
            )

        total_warga = Warga.query.count()
        total_keluarga = Keluarga.query.count()
        total_program = ProgramBantuan.query.filter_by(is_active=True).count()
        total_verifikasi = Verifikasi.query.count()

        # Statistik Pengajuan Perubahan Desil
        total_pengajuan_desil = PengajuanDesil.query.count()
        pengajuan_desil_menunggu = PengajuanDesil.query.filter_by(status="menunggu").count()

        # Statistik status verifikasi
        verif_layak = Verifikasi.query.filter(
            db.or_(
                Verifikasi.status_final == "layak",
                db.and_(Verifikasi.status_final == None, Verifikasi.status_otomatis == "layak")
            )
        ).count()

        verif_tidak_layak = Verifikasi.query.filter(
            db.or_(
                Verifikasi.status_final == "tidak_layak",
                db.and_(Verifikasi.status_final == None, Verifikasi.status_otomatis == "tidak_layak")
            )
        ).count()

        verif_perlu_tinjau = Verifikasi.query.filter(
            db.or_(
                Verifikasi.status_final == "perlu_ditinjau",
                db.and_(Verifikasi.status_final == None, Verifikasi.status_otomatis == "perlu_ditinjau")
            )
        ).count()

        verif_pending = Verifikasi.query.filter_by(status_final=None).count()

        # Riwayat verifikasi terbaru (5 data)
        recent_verifikasi = Verifikasi.query.order_by(Verifikasi.tanggal_verifikasi.desc()).limit(5).all()

        return render_template(
            "dashboard.html",
            total_warga=total_warga,
            total_keluarga=total_keluarga,
            total_program=total_program,
            total_verifikasi=total_verifikasi,
            total_pengajuan_desil=total_pengajuan_desil,
            pengajuan_desil_menunggu=pengajuan_desil_menunggu,
            verif_layak=verif_layak,
            verif_tidak_layak=verif_tidak_layak,
            verif_perlu_tinjau=verif_perlu_tinjau,
            verif_pending=verif_pending,
            recent_verifikasi=recent_verifikasi
        )

    # Template filters
    @app.template_filter("rupiah")
    def rupiah_filter(value):
        try:
            val = float(value or 0)
            return f"Rp {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(value)

    # Custom Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return render_template("errors/413.html"), 413

    return app
