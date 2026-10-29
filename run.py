import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from app import create_app, db
from app.models import User, Keluarga, Warga, ProgramBantuan, Verifikasi
import threading

app = create_app(os.environ.get("FLASK_ENV", "development"))

def _prewarm_ocr():
    try:
        from app.ocr_kk import get_reader
        get_reader()
    except Exception:
        pass

# Inisialisasi model OCR di background thread agar tidak menghambat startup
threading.Thread(target=_prewarm_ocr, daemon=True, name="OCRPrewarmThread").start()

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
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    app.run(host=host, port=port, debug=debug_mode)
