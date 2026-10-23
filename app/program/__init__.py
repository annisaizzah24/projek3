from flask import Blueprint

program_bp = Blueprint("program", __name__, url_prefix="/program")

from app.program import routes
