import os
from app import create_app, db
from app.models import User, Keluarga, Warga, ProgramBantuan, Verifikasi

app = create_app(os.environ.get("FLASK_ENV", "development"))

@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "User": User,
        "Keluarga": Keluarga,
        "Warga": Warga,
        "ProgramBantuan": ProgramBantuan,
        "Verifikasi": Verifikasi
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
