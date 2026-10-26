import re
import cv2
import easyocr

# Dibuat sekali saja saat server start, jangan di dalam fungsi
reader = easyocr.Reader(['id', 'en'], gpu=False)

def preprocess(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

def baca_kk(path):
    img = preprocess(path)
    lines = reader.readtext(img, detail=0, paragraph=False)
    teks = "\n".join(lines)

    # Nomor KK: 16 digit angka
    no_kk = re.search(r'\b\d{16}\b', teks.replace(" ", ""))

    # Nama kepala keluarga
    kepala = re.search(r'Kepala\s*Keluarga\s*[:\-]?\s*(.+)', teks, re.IGNORECASE)

    # Alamat
    alamat = re.search(r'Alamat\s*[:\-]?\s*(.+)', teks, re.IGNORECASE)

    return {
        "no_kk": no_kk.group(0) if no_kk else "",
        "kepala_keluarga": kepala.group(1).strip() if kepala else "",
        "alamat": alamat.group(1).strip() if alamat else "",
        "raw": teks,
    }