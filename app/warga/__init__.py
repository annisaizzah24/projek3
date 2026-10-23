from flask import Blueprint

warga_bp = Blueprint("warga", __name__)

from app.warga import routes
