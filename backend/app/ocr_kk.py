import sys
import os
import re
import time
import cv2
import numpy as np
from PIL import Image, ImageOps

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

_reader = None

def get_reader():
    """Mengembalikan instance EasyOCR Reader (singleton)."""
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(['id', 'en'], gpu=False, verbose=False)
        except ImportError:
            raise RuntimeError("Modul 'easyocr' belum terpasang. Silakan install dengan: pip install easyocr")
    return _reader


# Pemetaan karakter OCR yang sering tertukar antara huruf dan angka pada dokumen resmi
DIGIT_FIX = {
    'O': '0', 'o': '0', 'D': '0', 'Q': '0',
    'I': '1', 'l': '1', '|': '1', 'i': '1', '!': '1', ']': '1', 'j': '1', '/': '1',
    'Z': '2', 'z': '2',
    'E': '3',
    'A': '4',
    'S': '5', 's': '5',
    'b': '6', 'G': '6', 'L': '6',
    'T': '7',
    'B': '8',
    'g': '9', 'q': '9'
}

# Daftar 38 Kode Provinsi Resmi Indonesia (Permendagri / BPS)
PROVINSI_VALID = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 21,  # Sumatera
    31, 32, 33, 34, 35, 36,                  # Jawa
    51, 52, 53,                              # Bali & Nusa Tenggara
    61, 62, 63, 64, 65,                      # Kalimantan
    71, 72, 73, 74, 75, 76,                  # Sulawesi
    81, 82,                                  # Maluku
    91, 92, 93, 94, 95, 96, 97               # Papua
}

# Pembatas pemotong metadata agar tidak mengambil kolom tetangga
PEMOTONG_METADATA = r'\s+(?:Desa|Kelurahan|Kecam|Kabup|Kab\w*[/\\]?Kota|Kota\b|Provinsi|Kode\s*Pos|RT\s*[/\\I|]?\s*RW|Kewarga)'

# Kata-kata yang tidak boleh menjadi nama orang (label instansi/dokumen)
LARANG_NAMA = (
    "dinas", "kependudukan", "pencatatan", "sipil", "alamat", "desa",
    "kelurahan", "kecamatan", "kabupaten", "provinsi", "kode pos", "kartu", "keluarga",
    "republik", "indonesia", "nomor", "nama", "nik"
)


def clean_digits(s):
    """Membersihkan string kandidat nomor KK dengan pemetaan karakter OCR."""
    res = []
    for c in s:
        if c.isdigit():
            res.append(c)
        elif c in DIGIT_FIX:
            res.append(DIGIT_FIX[c])
    return "".join(res)


def valid_no_kk(s):
    """
    Validasi format Nomor KK Indonesia:
    1. Tepat 16 digit numerik.
    2. Dua digit pertama merupakan kode provinsi yang terdaftar sah.
    """
    if not s or len(s) != 16 or not s.isdigit():
        return False
    prov = int(s[:2])
    return prov in PROVINSI_VALID


def muat_gambar(path, max_dimension=1600):
    """
    Muat gambar dari path, lakukan koreksi EXIF orientation,
    dan sesuaikan resolusi agar detail teks optimal tanpa membebani CPU (maks ~1600px).
    """
    img_pil = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    max_dim = max(img_bgr.shape[:2])
    if max_dim > max_dimension:
        skala = max_dimension / max_dim
        img_bgr = cv2.resize(img_bgr, None, fx=skala, fy=skala, interpolation=cv2.INTER_AREA)
    elif max_dim < 1200:
        skala = 1400 / max_dim
        img_bgr = cv2.resize(img_bgr, None, fx=skala, fy=skala, interpolation=cv2.INTER_CUBIC)

    return img_bgr


def tingkatkan_kontras(gray):
    """Meningkatkan kontras gambar dokumen menggunakan CLAHE."""
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    return clahe.apply(gray)


def luruskan(gray):
    """Meluruskan kemiringan kecil (deskew) foto KK menggunakan garis horizontal."""
    try:
        edges = cv2.Canny(gray, 50, 150)
        garis = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=120,
            minLineLength=max(30, gray.shape[1] // 5), maxLineGap=20
        )
        if garis is None:
            return gray
        sudut = []
        for x1, y1, x2, y2 in garis.reshape(-1, 4):
            a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(a) < 15:
                sudut.append(a)
        if not sudut:
            return gray
        a = float(np.median(sudut))
        if abs(a) < 0.5:
            return gray
        h, w = gray.shape
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return gray


def koreksi_orientasi(img_bgr, reader, deadline=None):
    """
    Koreksi otomatis rotasi dokumen (0, 90 CW, 180, 270 CW) menggunakan thumbnail cepat.
    Mendeteksi orientasi tegak dokumen berdasarkan kata kunci resmi Kartu Keluarga.
    """
    h, w = img_bgr.shape[:2]
    # Dokumen KK di Indonesia berformat landscape (lebar > tinggi).
    # Jika foto portrait (tinggi > lebar), kandidat terkuat adalah rotasi 90 CW atau 270 CW.
    if h > w:
        rotasi_list = [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, None, cv2.ROTATE_180]
    else:
        rotasi_list = [None, cv2.ROTATE_180, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE]

    terbaik_img = img_bgr
    skor_terbaik = -1

    for rot in rotasi_list:
        if deadline and time.time() > deadline:
            break

        test_img = img_bgr if rot is None else cv2.rotate(img_bgr, rot)
        th_h, th_w = test_img.shape[:2]
        thumb = cv2.resize(test_img, (720, int(720 * th_h / th_w)))
        top_crop = thumb[:int(thumb.shape[0] * 0.40), :]
        gray_top = cv2.cvtColor(top_crop, cv2.COLOR_BGR2GRAY)
        enhanced_top = tingkatkan_kontras(gray_top)

        hasil_top = reader.readtext(enhanced_top)
        teks_gabung = " ".join(t[1].lower() for t in hasil_top)

        skor = 0
        if any(k in teks_gabung for k in ["kartu keluarga", "kartu kiluarga", "kartu klluarga"]):
            skor += 100
        elif "kartu" in teks_gabung and any(k in teks_gabung for k in ["keluarga", "kiluarga", "klluarga", "kel"]):
            skor += 90
        elif "kartu" in teks_gabung:
            skor += 40
        elif "keluarga" in teks_gabung:
            skor += 35

        if "republik" in teks_gabung or "indonesia" in teks_gabung:
            skor += 30
        if "kepala keluarga" in teks_gabung or "kepala" in teks_gabung:
            skor += 25
        if "desa" in teks_gabung or "kecamatan" in teks_gabung:
            skor += 15
        if re.search(r'\b(?:no\.?|nomor)\s*[:.\-]?\s*\d{10,16}', teks_gabung):
            skor += 40

        if skor > skor_terbaik:
            skor_terbaik = skor
            terbaik_img = test_img

        # Early exit jika sudah yakin orientasi benar (menghindari uji rotasi yang tidak perlu)
        if skor >= 40:
            break

    return terbaik_img


def susun_baris_dari_items(items):
    """Menggabungkan item bounding box yang sejajar horizontal menjadi baris teks terstruktur."""
    sorted_items = sorted(items, key=lambda i: i["yc"])
    baris = []
    for it in sorted_items:
        if baris and abs(it["yc"] - baris[-1]["yc"]) < max(it["h"], baris[-1]["h"]) * 0.6:
            baris[-1]["items"].append(it)
        else:
            baris.append({"yc": it["yc"], "h": it["h"], "items": [it]})

    lines = []
    for b in baris:
        b["items"].sort(key=lambda i: i["xmin"])
        lines.append(" ".join(i["text"] for i in b["items"]))
    return lines


def ekstrak_elemen(reader, enhanced_gray):
    """Mengekstrak seluruh elemen teks beserta informasi bounding box dan posisi spasialnya."""
    raw_results = reader.readtext(enhanced_gray, detail=1)
    img_h, img_w = enhanced_gray.shape[:2]
    items = []
    for bbox, text, conf in raw_results:
        t = text.strip()
        if not t:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        xmin, xmax = float(min(xs)), float(max(xs))
        ymin, ymax = float(min(ys)), float(max(ys))
        items.append({
            'text': t,
            'conf': float(conf),
            'bbox': bbox,
            'xmin': xmin, 'xmax': xmax,
            'ymin': ymin, 'ymax': ymax,
            'xc': (xmin + xmax) / 2.0,
            'yc': (ymin + ymax) / 2.0,
            'w': max(1.0, xmax - xmin),
            'h': max(1.0, ymax - ymin),
            'norm_x': ((xmin + xmax) / 2.0) / img_w,
            'norm_y': ((ymin + ymax) / 2.0) / img_h,
        })
    return items


def cari_batas_tabel(items, img_h):
    """
    Mencari batas atas tabel anggota keluarga (kolom NIK, Nama Lengkap, Tempat Lahir, dsb).
    Semua teks dan angka di bawah batas ini adalah data anggota keluarga / NIK
    dan SECARA TEGAS DILARANG dijadikan Nomor Kartu Keluarga.
    """
    table_y = None
    for it in items:
        if re.search(r'\b(?:nik|nama\s*lengkap|jenis\s*kelamin|tempat\s*lahir|tanggal\s*lahir|agama|pendidikan|pekerjaan)\b', it['text'], re.IGNORECASE):
            if table_y is None or it['ymin'] < table_y:
                table_y = it['ymin']

    if table_y is None:
        table_y = img_h * 0.32

    return table_y


def cari_nomor_kk(items, reader, enhanced_gray, table_y, img_h, img_w, deadline=None):
    """
    Mencari Nomor Kartu Keluarga (16 digit) secara spesifik dari header dokumen KK.
    Aturan Ketat:
    1. Nomor KK harus berada di bagian header (di atas batas tabel keluarga).
    2. Menolak seluruh NIK anggota keluarga dari tabel tabel 1 & 2.
    3. Menolak nomor registrasi / blanko dokumen (seperti 'No. K' pada margin pojok kanan atas).
    4. Menggunakan targeted re-OCR dengan numeric allowlist hanya jika diperlukan.
    5. Memvalidasi 16 digit angka dengan kode provinsi sah di Indonesia.
    """
    title_item = None
    for it in items:
        if it['yc'] < table_y and re.search(r'\bkartu\s*k[a-z]*\b', it['text'], re.IGNORECASE):
            title_item = it
            break

    kandidat = []
    reocr_cache = {}

    def uji_dan_tambah(cand_str, score, conf, item_ref, metode):
        cleaned = clean_digits(cand_str)
        if valid_no_kk(cleaned):
            kandidat.append({
                'no_kk': cleaned,
                'score': score,
                'conf': conf,
                'item': item_ref,
                'metode': metode
            })

    def reocr_kotak(xmin, ymin, xmax, ymax):
        """Re-OCR area kotak kandidat khusus angka numerik dengan caching."""
        if reader is None or enhanced_gray is None:
            return None, 0.0
        if deadline and time.time() > deadline:
            return None, 0.0

        key = (int(xmin // 4), int(ymin // 4), int(xmax // 4), int(ymax // 4))
        if key in reocr_cache:
            return reocr_cache[key]

        pad = 6
        x1 = max(0, int(xmin) - pad)
        y1 = max(0, int(ymin) - pad)
        x2 = min(img_w, int(xmax) + pad)
        y2 = min(img_h, int(ymax) + pad)
        if x2 - x1 < 10 or y2 - y1 < 6:
            reocr_cache[key] = (None, 0.0)
            return None, 0.0

        crop = enhanced_gray[y1:y2, x1:x2]
        res = reader.readtext(crop, allowlist='0123456789')
        if res:
            ans = (res[0][1].strip(), float(res[0][2]))
        else:
            ans = (None, 0.0)
        reocr_cache[key] = ans
        return ans

    for it in items:
        # ATURAN 1: STRICT EXCLUSION - Abaikan semua elemen di area tabel keluarga
        if it['yc'] >= table_y - 8:
            continue

        # ATURAN 2: STRICT EXCLUSION - Abaikan nomor registrasi dokumen pojok kanan atas
        if re.search(r'\bno\.?\s*[kK]\b', it['text'], re.IGNORECASE) or (it['norm_x'] > 0.65 and it['norm_y'] < 0.08):
            continue

        # ATURAN 3: STRICT EXCLUSION - Abaikan label NIK
        if re.search(r'\bnik\b', it['text'], re.IGNORECASE):
            continue

        # Pola 1: Label No. KK dan angka berada dalam satu bounding box
        # Contoh: "No. 6303082609160005" atau "No · 6303082609160005"
        m = re.search(r'(?:no\.?|no\s*kk|nomor\s*kk|nomor)\s*[:.\-·]?\s*([0-9a-zA-Z]{12,20})', it['text'], re.IGNORECASE)
        if m:
            raw_cand = m.group(1)
            cleaned = clean_digits(raw_cand)
            if valid_no_kk(cleaned):
                uji_dan_tambah(raw_cand, 190, it['conf'], it, "same_box_clean")
            else:
                re_dig, re_conf = reocr_kotak(it['xmin'], it['ymin'], it['xmax'], it['ymax'])
                if re_dig:
                    uji_dan_tambah(re_dig, 180, re_conf, it, "same_box_reocr")

        # Pola 2: Label "No", "No.", "No-KK", "Nomor" berada di satu box terpisah
        # dan nomor berada di box tepat di sebelah kanannya pada garis horizontal yang sama
        if re.match(r'^(?:no\.?|no\s*[-_]?\s*kk|nomor(?:\s*kk)?|no\s*[:.\-·])$', it['text'], re.IGNORECASE):
            for other in items:
                if other == it or other['yc'] >= table_y - 8:
                    continue
                dx = other['xmin'] - it['xmax']
                dy = abs(other['yc'] - it['yc'])
                if -10 <= dx <= it['h'] * 6 and dy <= it['h'] * 0.8:
                    cleaned_other = clean_digits(other['text'])
                    if valid_no_kk(cleaned_other):
                        uji_dan_tambah(other['text'], 200, other['conf'], other, "adjacent_cleaned")
                    else:
                        re_dig, re_conf = reocr_kotak(other['xmin'], other['ymin'], other['xmax'], other['ymax'])
                        if re_dig:
                            uji_dan_tambah(re_dig, 180, re_conf, other, "adjacent_allowlist")

        # Pola 3: Nomor berada tepat di bawah judul "KARTU KELUARGA" di bagian tengah header
        if title_item:
            dy = it['ymin'] - title_item['ymax']
            dx = abs(it['xc'] - title_item['xc'])
            if 0 < dy <= title_item['h'] * 3.5 and dx <= title_item['w'] * 0.6:
                cleaned_title = clean_digits(it['text'])
                if valid_no_kk(cleaned_title):
                    uji_dan_tambah(it['text'], 170, it['conf'], it, "under_title_cleaned")
                else:
                    re_dig, re_conf = reocr_kotak(it['xmin'], it['ymin'], it['xmax'], it['ymax'])
                    if re_dig:
                        uji_dan_tambah(re_dig, 150, re_conf, it, "under_title_reocr")

    if not kandidat:
        return "", "Nomor Kartu Keluarga (KK) tidak dapat diidentifikasi secara pasti dari header dokumen. Silakan periksa dokumen dan masukkan 16 digit Nomor KK secara manual."

    # Urutkan berdasarkan skor kesesuaian prioritas tertinggi lalu tingkat keyakinan (confidence)
    kandidat.sort(key=lambda k: (k['score'], k['conf']), reverse=True)
    return kandidat[0]['no_kk'], ""


def cari_kepala_keluarga(items, lines, table_y):
    """
    Ekstrak Nama Kepala Keluarga dari bagian metadata header dokumen (label 'Nama Kepala Keluarga').
    Menolak nama yang berasal dari tabel anggota keluarga.
    """
    # Strategi 1: Cari dari baris teks gabungan
    for line in lines[:15]:
        m = re.search(r'(?:nama\s*)?kepala\s*\w+\s*[:.\-]?\s*(.*)', line, re.IGNORECASE)
        if m:
            val = re.split(PEMOTONG_METADATA, m.group(1), flags=re.IGNORECASE)[0].strip(' :;.-')
            if val and not any(k in val.lower() for k in LARANG_NAMA) and not val.isdigit():
                return val

    # Strategi 2: Bounding box di samping kanan label 'Nama Kepala Keluarga'
    label_item = None
    for it in items:
        if it['yc'] < table_y and re.search(r'kepala\s*\w+', it['text'], re.IGNORECASE):
            label_item = it
            break

    if label_item:
        calon = []
        for other in items:
            if other == label_item or other['yc'] >= table_y:
                continue
            dx = other['xmin'] - label_item['xmax']
            dy = abs(other['yc'] - label_item['yc'])
            if 0 <= dx <= 350 and dy <= max(label_item['h'], other['h']) * 0.9:
                if other['norm_x'] < 0.60:
                    calon.append(other)
        if calon:
            calon.sort(key=lambda c: c['xmin'])
            nama = " ".join(c['text'] for c in calon).strip(' :;.-')
            nama = re.split(PEMOTONG_METADATA, nama, flags=re.IGNORECASE)[0].strip()
            if nama and not any(k in nama.lower() for k in LARANG_NAMA) and not nama.isdigit():
                return nama

    return ""


def cari_alamat(items, lines, table_y):
    """
    Ekstrak Alamat Domisili Keluarga dari metadata header dokumen.
    """
    # Strategi 1: Cek baris berlabel 'Alamat'
    for i, line in enumerate(lines[:10]):
        m = re.search(r'(?:alamat|aamal|almat)\s*[:.\-]?\s*(.*)', line, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            val = re.split(PEMOTONG_METADATA, val, flags=re.IGNORECASE)[0].strip(' :;.-')
            if val and val.lower() not in ('alamat', 'desa/kelurahan', 'desa', 'rt/rw', 'kecamatan'):
                return val

    # Strategi 2: Baris tepat di bawah 'Nama Kepala Keluarga' (layout standar KK)
    for i, line in enumerate(lines[:8]):
        if re.search(r'kepala\s*\w+', line, re.IGNORECASE):
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if not re.search(r'\b(?:rt\s*[/\\I|]?\s*rw|nik|nama\s*lengkap)\b', next_line, re.IGNORECASE):
                    val = re.split(PEMOTONG_METADATA, next_line, flags=re.IGNORECASE)[0].strip(' :;.-')
                    val = re.sub(r'^(?:alamat|aamal|almat)\s*[:.\-]?\s*', '', val, flags=re.IGNORECASE).strip(' :;.-')
                    if val and val.lower() not in ('alamat', 'desa/kelurahan', 'desa', 'rt/rw', 'kecamatan'):
                        return val

    # Strategi 3: Bounding box di samping label 'Alamat'
    for it in items:
        if it['yc'] < table_y and re.search(r'^(?:alamat|aamal|almat)\b', it['text'], re.IGNORECASE):
            for other in items:
                if other['yc'] < table_y and other['xmin'] > it['xmax'] and abs(other['yc'] - it['yc']) <= max(it['h'], other['h']) * 0.9:
                    if other['norm_x'] < 0.58:
                        val = other['text'].strip(' :;.-')
                        if val and val.lower() not in ('alamat', 'desa/kelurahan', 'desa', 'rt/rw', 'kecamatan'):
                            return val

    return ""


def baca_kk(path, timeout=60):
    """
    Fungsi utama OCR untuk memindai dokumen Kartu Keluarga dengan proteksi timeout:
    1. Memuat gambar dan memutar dokumen ke orientasi tegak secara cepat.
    2. Meningkatkan kontras (CLAHE) dan meluruskan kemiringan sudut (deskew).
    3. Ekstraksi dua tahap: memprioritaskan pemindaian zona header (45% atas) untuk kecepatan tinggi.
    4. Mendeteksi batas atas tabel keluarga untuk mengabaikan seluruh NIK tabel.
    5. Mengidentifikasi Nomor KK (16 digit), Kepala Keluarga, dan Alamat dari header.
    6. Mencegah pemrosesan berlebih dengan batas timeout yang dapat dikonfigurasi.
    """
    start_time = time.time()
    deadline = start_time + timeout

    reader = get_reader()

    # 1. Muat gambar (resolusi optimal max 1600px)
    img_bgr = muat_gambar(path, max_dimension=1600)

    # 2. Koreksi orientasi (0, 90, 180, 270 derajat) dengan batas waktu
    upright_bgr = koreksi_orientasi(img_bgr, reader, deadline=deadline)

    # 3. Grayscale, deskew, dan CLAHE
    gray = cv2.cvtColor(upright_bgr, cv2.COLOR_BGR2GRAY)
    gray = luruskan(gray)
    enhanced_gray = tingkatkan_kontras(gray)
    img_h, img_w = enhanced_gray.shape[:2]

    # 4. Tahap 1: Ekstraksi Cepat Zona Header (45% atas dokumen KK)
    top_h = int(img_h * 0.45)
    header_crop = enhanced_gray[:top_h, :]
    raw_results = reader.readtext(header_crop, detail=1)

    items = []
    for bbox, text, conf in raw_results:
        t = text.strip()
        if not t:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        xmin, xmax = float(min(xs)), float(max(xs))
        ymin, ymax = float(min(ys)), float(max(ys))
        items.append({
            'text': t,
            'conf': float(conf),
            'bbox': bbox,
            'xmin': xmin, 'xmax': xmax,
            'ymin': ymin, 'ymax': ymax,
            'xc': (xmin + xmax) / 2.0,
            'yc': (ymin + ymax) / 2.0,
            'w': max(1.0, xmax - xmin),
            'h': max(1.0, ymax - ymin),
            'norm_x': ((xmin + xmax) / 2.0) / img_w,
            'norm_y': ((ymin + ymax) / 2.0) / img_h,
        })

    lines = susun_baris_dari_items(items)
    table_y = cari_batas_tabel(items, img_h)
    no_kk, peringatan = cari_nomor_kk(items, reader, enhanced_gray, table_y, img_h, img_w, deadline=deadline)
    kepala_keluarga = cari_kepala_keluarga(items, lines, table_y)
    alamat = cari_alamat(items, lines, table_y)

    # 5. Tahap 2: Fallback ke pemindaian seluruh gambar hanya jika No KK belum ditemukan
    # dan masih ada sisa waktu sebelum deadline timeout
    if not no_kk and (time.time() < deadline - 5):
        full_results = reader.readtext(enhanced_gray, detail=1)
        items_full = []
        for bbox, text, conf in full_results:
            t = text.strip()
            if not t:
                continue
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            xmin, xmax = float(min(xs)), float(max(xs))
            ymin, ymax = float(min(ys)), float(max(ys))
            items_full.append({
                'text': t,
                'conf': float(conf),
                'bbox': bbox,
                'xmin': xmin, 'xmax': xmax,
                'ymin': ymin, 'ymax': ymax,
                'xc': (xmin + xmax) / 2.0,
                'yc': (ymin + ymax) / 2.0,
                'w': max(1.0, xmax - xmin),
                'h': max(1.0, ymax - ymin),
                'norm_x': ((xmin + xmax) / 2.0) / img_w,
                'norm_y': ((ymin + ymax) / 2.0) / img_h,
            })
        lines_full = susun_baris_dari_items(items_full)
        table_y_full = cari_batas_tabel(items_full, img_h)
        no_kk, peringatan = cari_nomor_kk(items_full, reader, enhanced_gray, table_y_full, img_h, img_w, deadline=deadline)
        if not kepala_keluarga:
            kepala_keluarga = cari_kepala_keluarga(items_full, lines_full, table_y_full)
        if not alamat:
            alamat = cari_alamat(items_full, lines_full, table_y_full)
        lines = lines_full

    elapsed = time.time() - start_time
    return {
        "no_kk": no_kk,
        "kepala_keluarga": kepala_keluarga,
        "alamat": alamat,
        "peringatan": peringatan,
        "raw": "\n".join(lines),
        "duration_seconds": round(elapsed, 2)
    }