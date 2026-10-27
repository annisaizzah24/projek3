import re
import cv2
import numpy as np
import easyocr
from PIL import Image, ImageOps

reader = easyocr.Reader(['id', 'en'], gpu=False)

DIGIT_FIX = str.maketrans({
    'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'I': '1', 'l': '1',
    '|': '1', 'S': '5', 'B': '8', 'Z': '2'
})

PROVINSI_VALID = {11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 31, 32, 33, 34, 35, 36,
                  51, 52, 53, 61, 62, 63, 64, 65, 71, 72, 73, 74, 75, 76, 81, 82,
                  91, 92, 93, 94, 95, 96, 97}

PEMOTONG = r'\s+(?:Desa|Kelurahan|Kecam|Kabup|Kab\w*[/\\]?Kota|Kota\b|Provinsi|Kode\s*Pos|RT\s*[/\\I|]?\s*RW|Kewarga)'
LARANG_NAMA = ("dinas", "kependudukan", "pencatatan", "sipil", "alamat",
               "desa", "kelurahan", "kecamatan", "kabupaten", "provinsi", "kode pos")


def muat_gambar(path):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    skala = 1600 / max(img.shape[:2])
    img = cv2.resize(img, None, fx=skala, fy=skala, interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def luruskan(gray):
    """Luruskan foto yang miring memakai garis-garis tabel/teks di KK."""
    edges = cv2.Canny(gray, 50, 150)
    garis = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=150,
                            minLineLength=gray.shape[1] // 4, maxLineGap=20)
    if garis is None:
        return gray
    sudut = []
    for x1, y1, x2, y2 in garis.reshape(-1, 4):
        a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(a) < 30:
            sudut.append(a)
    if not sudut:
        return gray
    a = float(np.median(sudut))
    if abs(a) < 0.5:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)

def susun_baris(hasil):
    """Gabungkan potongan teks yang sejajar menjadi satu baris."""
    items = []
    for bbox, teks, _ in hasil:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        items.append({"x": min(xs), "yc": (min(ys) + max(ys)) / 2,
                      "h": max(ys) - min(ys), "t": teks.strip()})
    items.sort(key=lambda i: i["yc"])

    baris = []
    for it in items:
        if baris and abs(it["yc"] - baris[-1]["yc"]) < max(it["h"], baris[-1]["h"]) * 0.6:
            baris[-1]["items"].append(it)
        else:
            baris.append({"yc": it["yc"], "h": it["h"], "items": [it]})

    lines = []
    for b in baris:
        b["items"].sort(key=lambda i: i["x"])
        lines.append(" ".join(i["t"] for i in b["items"]))
    return lines


def valid_no_kk(s):
    return (len(s) == 16 and int(s[:2]) in PROVINSI_VALID
            and 1 <= int(s[8:10]) <= 12)


def cari_no_kk(lines):
    kandidat = []
    for line in lines[:12]:
        for tok in re.findall(r'[0-9OoDQIl|SBZ]{10,}', line):
            if sum(c.isdigit() for c in tok) < 8:
                continue
            d = tok.translate(DIGIT_FIX)
            if d.isdigit():
                kandidat.append(d)

    for d in kandidat:
        if valid_no_kk(d):
            return d, ""

    # Tidak ada yang 16 digit: ambil yang paling panjang, beri peringatan
    for d in sorted(kandidat, key=len, reverse=True):
        if 13 <= len(d) <= 18 and int(d[:2]) in PROVINSI_VALID:
            return d, f"Nomor KK terbaca {len(d)} digit (seharusnya 16). Periksa dan lengkapi manual."
    return "", ""


def ambil_nilai(lines, kunci, larang=()):
    for i, line in enumerate(lines[:25]):
        m = re.search(kunci + r'\s*[:;.\-]?\s*(.*)', line, re.IGNORECASE)
        if not m:
            continue
        nilai = m.group(1)
        if not nilai.strip(' :;.-') and i + 1 < len(lines):
            nilai = lines[i + 1]
        nilai = re.split(PEMOTONG, nilai, flags=re.IGNORECASE)[0].strip(' :;.-')
        if nilai and not any(k in nilai.lower() for k in larang):
            return nilai
    return ""


def baca_kk(path):
    gray = luruskan(muat_gambar(path))
    putaran = (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180,
               cv2.ROTATE_90_COUNTERCLOCKWISE)

    terbaik, skor_terbaik = None, (-1, -1)
    for putar in putaran:
        g = gray if putar is None else cv2.rotate(gray, putar)
        lines = susun_baris(reader.readtext(g, detail=1, paragraph=False))
        no_kk, peringatan = cari_no_kk(lines)
        ada_kata = "keluarga" in " ".join(lines).lower()
        skor = (int(bool(no_kk)), int(ada_kata))
        if skor > skor_terbaik:
            terbaik, skor_terbaik = (lines, no_kk, peringatan), skor
        if no_kk or ada_kata:
            break

    lines, no_kk, peringatan = terbaik
    print("=== HASIL MENTAH OCR ===")
    for i, l in enumerate(lines):
        print(i, repr(l))

    return {
        "no_kk": no_kk,
        "kepala_keluarga": ambil_nilai(lines, r'nama\s*kepala\s*k[e3]luarga', LARANG_NAMA),
        "alamat": ambil_nilai(lines, r'alamat'),
        "peringatan": peringatan,
        "raw": "\n".join(lines),
    }