from flask import Blueprint

desil_bp = Blueprint("desil", __name__)

from app.desil import routes
