from flask import Blueprint

verifikasi_bp = Blueprint("verifikasi", __name__, url_prefix="/verifikasi")

from app.verifikasi import routes
