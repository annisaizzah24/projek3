import os
import re
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Singleton PaddleOCR instance
_paddle_ocr_instance = None

KATA_STATUS_TERLARANG = {
    "kawin", "kaluign", "kaluwign", "kaluarga", "belum kawin", "anak", "istri",
    "suami", "famili", "orang tua", "ayah", "ibu", "laki-laki", "perempuan",
    "wni", "wna", "islam", "kristen", "katolik", "hindu", "buddha", "khonghucu",
    "kepala keluarga", "nama", "nik", "alamat", "rt/rw", "rt", "rw", "desa",
    "kelurahan", "kecamatan", "kabupaten", "kota", "provinsi", "agama", "pekerjaan"
}


def _get_ocr_engine():
    """Menginisialisasi PaddleOCR secara singleton dengan konfigurasi offline stabil."""
    global _paddle_ocr_instance
    if _paddle_ocr_instance is not None:
        return _paddle_ocr_instance

    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    paddlex_cache = os.path.join(workspace_dir, ".paddlex")

    os.environ["PADDLE_PDX_CACHE_HOME"] = paddlex_cache
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_use_onednn"] = "0"

    try:
        from paddleocr import PaddleOCR
        # Inisialisasi engine deteksi dan pengenalan teks (dioptimalkan tanpa per-line orientation check untuk performa cepat CPU)
        _paddle_ocr_instance = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
            text_recognition_batch_size=16,
            lang="en"
        )
        logger.info("PaddleOCR engine berhasil dimuat (mode cepat).")
    except Exception as e:
        logger.error(f"Gagal memuat PaddleOCR: {e}")
        raise

    return _paddle_ocr_instance


def _convert_pdf_to_image_if_needed(file_path: str) -> str:
    """Jika file adalah PDF, render halaman pertama ke file gambar sementara."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext != ".pdf":
        return file_path

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        if len(doc) == 0:
            raise ValueError("Dokumen PDF tidak memiliki halaman.")
        page = doc[0]
        # Render pada resolusi 200 DPI (zoom 2.0x) agar OCR akurat
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        temp_img = file_path + "_page1.png"
        pix.save(temp_img)
        doc.close()
        return temp_img
    except Exception as e:
        logger.warning(f"Gagal merender halaman PDF dengan PyMuPDF: {e}")
        return file_path


def _auto_orient_image(file_path: str) -> Tuple[str, bool]:
    """
    1. Dokumen fisik Kartu Keluarga (KK) selalu berorientasi Landscape (Lebar > Tinggi).
       Jika pengguna mengunggah foto vertikal/portrait (Tinggi > Lebar) dari kamera HP,
       putar otomatis 90 derajat searah jarum jam (270 derajat counter-clockwise) agar teks terbaca horizontal.
    2. Filter Area Baca (Region of Interest / ROI):
       9 data yang dibutuhkan (Nomor KK, Kepala Keluarga, Alamat, RT/RW, Desa, Kecamatan, Kab/Kota,
       Provinsi, dan NIK Kepala Keluarga) 100% berada di paruh atas (top 58%) dokumen KK.
       Memotong area bawah tabel anggota lain, tabel orang tua, dan tanda tangan memangkas
       lebih dari 50% beban kotak teks, sehingga waktu proses OCR berkurang drastis di bawah 1 menit.
    3. Normalisasi Resolusi Cerdas:
       Mereduksi gambar kamera HP (> 1200px) ke resolusi ideal tanpa mengurangi ketajaman huruf/angka.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return file_path, False

    try:
        from PIL import Image
        with Image.open(file_path) as im:
            w, h = im.size
            modified = False

            # 1. Putar otomatis jika foto portrait dari HP
            if h > w:
                im = im.rotate(270, expand=True)
                w, h = im.size
                modified = True
                logger.info(f"Otomatis memutar dokumen KK dari Portrait ke Landscape ({w}x{h}).")

            # 2. Ambil paruh atas dokumen (Header + Baris 1 Tabel Anggota Keluarga)
            # 9 data yang dibutuhkan (Nomor KK, Nama KK, Alamat, RT/RW, Desa, Kecamatan, Kab/Kota, Provinsi, NIK)
            # 100% berada di 32% teratas dokumen KK (memotong baris 2-10 tabel anggota keluarga).
            crop_h = int(h * 0.32)
            im = im.crop((0, 0, w, crop_h))
            w, h = im.size
            modified = True

            # 3. Masking cerdas pada area Tabel Anggota Keluarga:
            # Di area tabel (Y >= 24.5% dari tinggi dokumen), kolom 4-10 (X > 38% lebar)
            # dimasker putih agar AI tidak membuang waktu memproses 40+ kotak teks kecil
            # (Jenis Kelamin, Agama, Pekerjaan, dll) yang tidak dibutuhkan form.
            from PIL import ImageDraw
            draw = ImageDraw.Draw(im)
            table_start_y = int(h * (0.245 / 0.32))
            table_mask_x = int(w * 0.38)
            draw.rectangle([table_mask_x, table_start_y, w, h], fill=(255, 255, 255))

            # 4. Normalisasi Resolusi Cerdas ke 1000px untuk akselerasi kecepatan inferensi CPU & ketajaman angka NIK
            MAX_DIM = 1000
            if max(w, h) > MAX_DIM:
                ratio = MAX_DIM / max(w, h)
                new_w, new_h = int(w * ratio), int(h * ratio)
                im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                modified = True
                logger.info(f"Optimasi ukuran gambar KK ke {new_w}x{new_h} untuk kecepatan inferensi CPU.")

            if modified:
                temp_proc = file_path + "_auto_proc.jpg"
                im.convert("RGB").save(temp_proc, quality=95)
                return temp_proc, True
    except Exception as e:
        logger.warning(f"Gagal memeriksa/mengoptimasi gambar: {e}")

    return file_path, False


def bersihkan_teks(teks: str) -> str:
    """Membersihkan teks dari karakter non-alfanumerik berlebih."""
    if not teks:
        return ""
    teks = re.sub(r"^[^\w\d]+", "", teks)
    teks = re.sub(r"[^\w\d]+$", "", teks)
    return teks.strip()


def is_valid_person_name(name: str) -> bool:
    """Memeriksa apakah string merupakan nama orang yang valid, bukan status/label tabel."""
    if not name or len(name) < 3:
        return False
    name_clean = bersihkan_teks(name).lower()
    for bad in KATA_STATUS_TERLARANG:
        if name_clean == bad or name_clean.startswith(bad + " ") or name_clean.endswith(" " + bad):
            return False
    # Validasi alfabet
    alpha_chars = sum(c.isalpha() for c in name)
    return alpha_chars >= 3 and not re.search(r"\d", name)


def _get_box_center(b) -> Tuple[Optional[float], Optional[float]]:
    """Menghitung titik tengah (center_x, center_y) dari bounding box OCR."""
    if not b:
        return None, None
    if len(b) == 4 and isinstance(b[0], (int, float)):
        # [xmin, ymin, xmax, ymax]
        return (float(b[0]) + float(b[2])) / 2.0, (float(b[1]) + float(b[3])) / 2.0
    elif len(b) >= 4 and isinstance(b[0], (list, tuple)):
        # [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
        return sum(float(p[0]) for p in b) / len(b), sum(float(p[1]) for p in b) / len(b)
    return None, None


def _cluster_rows(items: list[dict], tol: float = 8.0) -> list[list[dict]]:
    """Mengelompokkan teks OCR yang berada pada baris horizontal yang sama (toleransi Y)."""
    sorted_items = sorted(items, key=lambda x: x["mid_y"])
    rows: list[list[dict]] = []
    for it in sorted_items:
        placed = False
        for r in rows:
            avg_y = sum(x["mid_y"] for x in r) / len(r)
            if abs(it["mid_y"] - avg_y) <= tol:
                r.append(it)
                placed = True
                break
        if not placed:
            rows.append([it])
    return rows


def ekstrak_informasi_kk(lines: list[dict]) -> Dict[str, Any]:
    """
    Mengekstrak informasi spesifik Kartu Keluarga dari daftar baris teks OCR:
    - nomor_kk (16 digit)
    - nik_kepala_keluarga (15/16 digit)
    - kepala_keluarga
    - alamat
    - rt_rw
    - desa_kelurahan
    - kecamatan
    - kabupaten_kota
    - provinsi
    """
    spatial_lines = []
    for item in lines:
        txt = item.get("text", "").strip()
        if not txt:
            continue
        cx, cy = _get_box_center(item.get("box"))
        spatial_lines.append({
            "text": txt,
            "mid_x": cx,
            "mid_y": cy,
            "box": item.get("box")
        })

    raw_texts = [it["text"] for it in spatial_lines]
    full_text = "\n".join(raw_texts)

    hasil: Dict[str, Optional[str]] = {
        "nomor_kk": None,
        "nik_kepala_keluarga": None,
        "kepala_keluarga": None,
        "alamat": None,
        "rt_rw": None,
        "desa_kelurahan": None,
        "kecamatan": None,
        "kabupaten_kota": None,
        "provinsi": None,
    }

    def clean_val(v: Optional[str]) -> str:
        if not v:
            return ""
        v = re.sub(r"^[:.\-\s]+", "", v)
        v = re.sub(r"[:.\-\s]+$", "", v)
        return v.strip()

    # 1. Nomor KK: cari 16 digit yang berada di header atau setelah kata 'No'/'Nomor'
    for it in spatial_lines:
        m = re.search(r"(?:no|nomor)?\.?\s*[:.\-]?\s*(\d{16})", it["text"], re.IGNORECASE)
        if m:
            hasil["nomor_kk"] = m.group(1)
            break

    if not hasil["nomor_kk"]:
        for it in spatial_lines:
            m = re.search(r"\b(\d{16})\b", it["text"])
            if m:
                hasil["nomor_kk"] = m.group(1)
                break

    # 2. Deteksi Batas Header dan Awal Tabel
    has_coords = any(it["mid_x"] is not None and it["mid_y"] is not None for it in spatial_lines)
    valid_items = [it for it in spatial_lines if it["mid_x"] is not None and it["mid_y"] is not None] if has_coords else []
    table_headers = [
        it for it in valid_items
        if re.search(r"nama\s*l[ae]ngkap|name\s*l[ae]ngkap|nik\b|jenis\s*kelamin|jenio|kelar?min", it["text"], re.I)
    ]
    header_y_max = min([it["mid_y"] for it in table_headers]) if table_headers else 9999.0

    # 3. NIK Kepala Keluarga: 16 digit angka di baris pertama tabel (atau selain Nomor KK)
    table_items = [it for it in spatial_lines if it["mid_y"] is not None and it["mid_y"] >= header_y_max]
    for it in table_items:
        m_nik = re.search(r"(\d{16})", it["text"])
        if m_nik and m_nik.group(1) != hasil["nomor_kk"]:
            hasil["nik_kepala_keluarga"] = m_nik.group(1)
            break
    if not hasil["nik_kepala_keluarga"]:
        for it in spatial_lines:
            m_nik = re.search(r"(\d{16})", it["text"])
            if m_nik and m_nik.group(1) != hasil["nomor_kk"]:
                hasil["nik_kepala_keluarga"] = m_nik.group(1)
                break
    if not hasil["nik_kepala_keluarga"]:
        for it in spatial_lines:
            m_nik = re.search(r"(\d{15,16})", it["text"])
            if m_nik and m_nik.group(1) != hasil["nomor_kk"]:
                hasil["nik_kepala_keluarga"] = m_nik.group(1)
                break

    # Harmonisasi kode wilayah NIK (6 digit pertama) jika terdapat kesalahan baca 1 digit OCR (misal 5 terbaca 6)
    if hasil["nomor_kk"] and hasil["nik_kepala_keluarga"] and len(hasil["nomor_kk"]) == 16 and len(hasil["nik_kepala_keluarga"]) == 16:
        kk_prefix = hasil["nomor_kk"][:6]
        nik_prefix = hasil["nik_kepala_keluarga"][:6]
        diff_count = sum(c1 != c2 for c1, c2 in zip(kk_prefix, nik_prefix))
        if diff_count == 1:
            hasil["nik_kepala_keluarga"] = kk_prefix + hasil["nik_kepala_keluarga"][6:]

    # 4. SPATIAL EXTRACTION: Pemisahan Kolom & Baris Header
    # Mendukung Format KK Tradisional maupun Modern (Desa/Kelurahan bisa di Kolom Kiri atau Kolom Kanan)
    if has_coords:
        header_items = [
            it for it in valid_items
            if 40.0 < it["mid_y"] < header_y_max - 5 and not re.search(r"^kartu\s*keluarga|^no\.", it["text"], re.I)
        ]
        if header_items:
            xs = [it["mid_x"] for it in header_items]
            col_split_x = (min(xs) + max(xs)) / 2.0

            left_items = [it for it in header_items if it["mid_x"] < col_split_x]
            right_items = [it for it in header_items if it["mid_x"] >= col_split_x]

            all_rows = _cluster_rows(left_items) + _cluster_rows(right_items)
            for r in all_rows:
                r_sorted = sorted(r, key=lambda x: x["mid_x"])
                first_txt = r_sorted[0]["text"].lower()
                val_txt = clean_val(" ".join(x["text"] for x in r_sorted[1:])) if len(r_sorted) > 1 else ""

                if not val_txt and ":" in r_sorted[0]["text"]:
                    parts = r_sorted[0]["text"].split(":", 1)
                    first_txt = parts[0].strip().lower()
                    val_txt = clean_val(parts[1])

                if "nama kepala keluarga" in first_txt and not hasil["kepala_keluarga"]:
                    if val_txt and is_valid_person_name(val_txt):
                        hasil["kepala_keluarga"] = val_txt
                elif re.search(r"^(?:ala[mrn]{2,4}at|alamat|alarnat|alfirwi)", first_txt) and not hasil["alamat"]:
                    val_clean = re.sub(r"\s*[0-9OoSs]{1,4}\s*[/]\s*[0-9OoSs\-]{1,4}.*", "", val_txt).strip()
                    if val_clean:
                        hasil["alamat"] = val_clean
                    elif val_txt:
                        hasil["alamat"] = val_txt
                elif re.search(r"^rt\s*[/.]?\s*rw", first_txt) and not hasil["rt_rw"]:
                    m_r = re.search(r"([0-9OoSs]{1,4})\s*[/]\s*([0-9OoSs\-]{1,4})?", val_txt)
                    if m_r:
                        r1 = m_r.group(1).upper().replace("S", "0").replace("O", "0")
                        r2 = (m_r.group(2) or "-").upper().replace("S", "0").replace("O", "0")
                        p1 = f"{int(r1):03d}" if r1.isdigit() else r1
                        p2 = f"{int(r2):03d}" if r2.isdigit() else (r2 if r2 else "-")
                        hasil["rt_rw"] = f"{p1}/{p2}"
                elif re.search(r"^desa\s*[/.]?\s*kelurahan", first_txt) and not hasil["desa_kelurahan"]:
                    if val_txt:
                        hasil["desa_kelurahan"] = val_txt
                elif re.search(r"^(?:kecamatan|kecanatan)", first_txt) and not hasil["kecamatan"]:
                    if val_txt:
                        hasil["kecamatan"] = val_txt
                elif re.search(r"^(?:kabupaten\s*[/.]?\s*kota|keluapteian/kota|keuapteian/kota|kabupatan/kota)", first_txt) and not hasil["kabupaten_kota"]:
                    if val_txt:
                        hasil["kabupaten_kota"] = val_txt
                elif re.search(r"^(?:provinsi|prooisi|proisi|proroisi)", first_txt) and not hasil["provinsi"]:
                    if val_txt:
                        hasil["provinsi"] = val_txt

    # 4. Fallback Scanning Label Berurutan (jika ada data yang belum terisi dari ekstraksi spasial)
    for i, l in enumerate(raw_texts):
        l_strip = l.strip()
        l_lower = l_strip.lower()

        # A. Nama Kepala Keluarga
        if not hasil["kepala_keluarga"] and re.search(r"^nama\s*kepala\s*keluarga", l_lower):
            m = re.search(r"^nama\s*kepala\s*keluarga\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if is_valid_person_name(cand):
                    hasil["kepala_keluarga"] = cand
            elif i + 1 < len(raw_texts):
                cand = clean_val(raw_texts[i + 1])
                if is_valid_person_name(cand) and not re.search(r"^(?:desa|alamat|rt|rw|no\.|kecamatan)", cand, re.I):
                    hasil["kepala_keluarga"] = cand

        # B. Alamat (dapat berupa Jalan, Gang, Blok, Dusun, atau Nama Desa tertentu)
        if not hasil["alamat"] and re.search(r"^(?:alamat|alfirwi)", l_lower):
            m = re.search(r"^alamat\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"^(?:rt\s*[/.]?\s*rw|kecamatan|kecanatan|kode\s*pos)", cand, re.I):
                    hasil["alamat"] = cand
            if not hasil["alamat"]:
                for offset in (1, 2):
                    if i + offset < len(raw_texts):
                        cand = clean_val(raw_texts[i + offset])
                        # Nilai alamat tidak boleh berupa label RT/RW, Kecamatan, Kode Pos, atau Kabupaten
                        if cand and not re.search(r"^(?:rt\s*[/.]?\s*rw|kecamatan|kecanatan|kode\s*pos|kabupaten|provinsi)", cand, re.I):
                            hasil["alamat"] = cand
                            break

        # C. RT / RW (format angka murni 005/001 atau angka dengan dash 003/-)
        if not hasil["rt_rw"] and re.search(r"^rt\s*[/.]?\s*rw", l_lower):
            m = re.search(r"^rt\s*[/.]?\s*rw\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            val_to_parse = ""
            if m and clean_val(m.group(1)):
                val_to_parse = clean_val(m.group(1))
            elif i + 1 < len(raw_texts):
                cand = clean_val(raw_texts[i + 1])
                if cand and not re.search(r"^(?:kode\s*pos|desa|kelurahan|kabupaten|provinsi)", cand, re.I):
                    val_to_parse = cand

            if val_to_parse:
                m_num = re.search(r"([0-9OoSs]{1,4})\s*[/]\s*([0-9OoSs\-]{1,4})?", val_to_parse)
                if m_num:
                    r1 = m_num.group(1).upper().replace("S", "0").replace("O", "0")
                    r2 = (m_num.group(2) or "-").upper().replace("S", "0").replace("O", "0")
                    p1 = f"{int(r1):03d}" if r1.isdigit() else r1
                    if r2.isdigit():
                        p2 = f"{int(r2):03d}"
                    else:
                        p2 = "-"
                    hasil["rt_rw"] = f"{p1}/{p2}"

        # D. Desa / Kelurahan
        if not hasil["desa_kelurahan"] and re.search(r"^desa\s*[/.]?\s*kelurahan", l_lower):
            m = re.search(r"^desa\s*[/.]?\s*kelurahan\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"^(?:kecamatan|kecanatan|kabupaten|provinsi)", cand, re.I):
                    hasil["desa_kelurahan"] = cand
            elif i + 1 < len(raw_texts):
                cand = clean_val(raw_texts[i + 1])
                if cand and not re.search(r"^(?:kecamatan|kecanatan|kabupaten|provinsi|alamat|rt)", cand, re.I):
                    hasil["desa_kelurahan"] = cand

        # E. Kecamatan
        if not hasil["kecamatan"] and re.search(r"^(?:kecamatan|kecanatan)", l_lower):
            m = re.search(r"^(?:kecamatan|kecanatan)\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"[\d/]", cand) and not re.search(r"^(?:kabupaten|keluapteian|keuapteian|provinsi)", cand, re.I):
                    hasil["kecamatan"] = cand
            elif i + 1 < len(raw_texts):
                for offset in (1, 2, 3, 4, 5, 6, 7):
                    if i + offset < len(raw_texts):
                        cand = clean_val(raw_texts[i + offset])
                        if cand and len(cand) >= 3 and not re.search(r"[\d/]", cand) and not re.search(r"^(?:kode|pos|kabupaten|keluapteian|keuapteian|provinsi|proroisi|desa|kelurahan|alamat|rt|jl)", cand, re.I):
                            hasil["kecamatan"] = cand
                            break

        # F. Kabupaten / Kota
        if not hasil["kabupaten_kota"] and re.search(r"^(?:kabupaten\s*[/.]?\s*kota|keluapteian/kota|keuapteian/kota)", l_lower):
            m = re.search(r"^(?:kabupaten\s*[/.]?\s*kota|keluapteian/kota|keuapteian/kota)\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"[\d/]", cand) and not re.search(r"^(?:provinsi|prooisi|proroisi)", cand, re.I):
                    hasil["kabupaten_kota"] = cand
            elif i + 1 < len(raw_texts):
                for offset in (1, 2):
                    if i + offset < len(raw_texts):
                        cand = clean_val(raw_texts[i + offset])
                        if cand and not re.search(r"[\d/]", cand) and not re.search(r"^(?:provinsi|prooisi|proroisi|kode|pos|kecamatan|desa|kelurahan)", cand, re.I):
                            hasil["kabupaten_kota"] = cand
                            break

        # G. Provinsi
        if not hasil["provinsi"] and re.search(r"^(?:provinsi|prooisi|proisi|proroisi)", l_lower):
            m = re.search(r"^(?:provinsi|prooisi|proisi|proroisi)\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"[\d/]", cand) and not re.search(r"^(?:no|nama|nik|kode|pos)", cand, re.I):
                    hasil["provinsi"] = cand
            elif i + 1 < len(raw_texts):
                cand = clean_val(raw_texts[i + 1])
                if cand and not re.search(r"[\d/]", cand) and not re.search(r"^(?:no|nama|nik|kode|pos)", cand, re.I):
                    hasil["provinsi"] = cand

    # 3. Fallback Alamat jika belum ketemu dari label: cari baris berawalan JL/Jalan/Dusun/Blok
    if not hasil["alamat"]:
        for l in raw_texts:
            if re.search(r"\b(?:jl|jln|jalan|gang|gg|dusun|ds|blok|komplek|kp)\b", l, re.IGNORECASE):
                cand = clean_val(re.sub(r"^alamat\s*[:.\-]?", "", l, flags=re.I))
                if len(cand) > 3:
                    hasil["alamat"] = cand
                    break

    # 4. Fallback RT/RW jika belum ketemu: cari pola regex di seluruh teks
    if not hasil["rt_rw"]:
        for l in raw_texts:
            m_rtrw = re.search(r"\b([0-9OoSs]{1,4}\s*[/]\s*[0-9OoSs\-]{1,4})", l)
            if m_rtrw:
                cand = m_rtrw.group(1).upper().replace("S", "0").replace("O", "0").replace(" ", "")
                parts = cand.split("/")
                p1 = f"{int(parts[0]):03d}" if parts[0].isdigit() else parts[0]
                p2 = f"{int(parts[1]):03d}" if parts[1].isdigit() else (parts[1] or "-")
                hasil["rt_rw"] = f"{p1}/{p2}"
                break

    # 5. Fallback Kepala Keluarga jika belum ketemu: Baris pertama tabel anggota keluarga
    if not hasil["kepala_keluarga"]:
        for i, line in enumerate(raw_texts):
            if re.search(r"nama\s*l[ae]ngkap", line, re.IGNORECASE):
                for offset in range(1, 20):
                    if i + offset < len(raw_texts):
                        cand = clean_val(raw_texts[i + offset])
                        if is_valid_person_name(cand):
                            hasil["kepala_keluarga"] = cand
                            break
                if hasil["kepala_keluarga"]:
                    break

    # 6. Fallback NIK Kepala Keluarga jika belum ketemu: 15-16 digit angka selain nomor KK
    if not hasil["nik_kepala_keluarga"]:
        for line in raw_texts:
            m_nik = re.search(r"(\d{15,16})", line)
            if m_nik:
                val = m_nik.group(1)
                if val != hasil["nomor_kk"]:
                    hasil["nik_kepala_keluarga"] = val
                    break

    # Harmonisasi kode wilayah NIK (6 digit pertama) dengan Nomor KK jika terdapat kesalahan baca 1 digit OCR
    if hasil["nomor_kk"] and hasil["nik_kepala_keluarga"] and len(hasil["nomor_kk"]) == 16 and len(hasil["nik_kepala_keluarga"]) == 16:
        kk_prefix = hasil["nomor_kk"][:6]
        nik_prefix = hasil["nik_kepala_keluarga"][:6]
        diff_count = sum(c1 != c2 for c1, c2 in zip(kk_prefix, nik_prefix))
        if diff_count <= 2 and (kk_prefix[:2] == nik_prefix[:2] or diff_count == 1):
            hasil["nik_kepala_keluarga"] = kk_prefix + hasil["nik_kepala_keluarga"][6:]

    return {
        "success": True,
        "data": hasil,
        "raw_text": full_text
    }


def baca_kk_paddle(file_path: str) -> Dict[str, Any]:
    """
    Membaca dokumen Kartu Keluarga (gambar JPG/PNG atau file PDF) menggunakan PaddleOCR.
    Mengembalikan dictionary hasil ekstraksi terstruktur.
    """
    if not file_path or not os.path.exists(file_path):
        return {
            "success": False,
            "error": "Berkas dokumen tidak ditemukan di server."
        }

    temp_files = []
    try:
        # Jika PDF, konversi halaman pertama ke gambar
        image_path = _convert_pdf_to_image_if_needed(file_path)
        if image_path != file_path:
            temp_files.append(image_path)

        # Periksa dan perbaiki orientasi otomatis (Portrait -> Landscape)
        oriented_path, is_temp = _auto_orient_image(image_path)
        if is_temp:
            temp_files.append(oriented_path)

        ocr = _get_ocr_engine()
        predictions = list(ocr.predict(oriented_path))

        lines = []
        if predictions:
            first_page = predictions[0]
            rec_texts = first_page.get("rec_texts", [])
            rec_scores = first_page.get("rec_scores", [])
            rec_boxes = first_page.get("rec_boxes", [])

            for t, s, b in zip(rec_texts, rec_scores, rec_boxes):
                lines.append({
                    "text": str(t).strip(),
                    "score": float(s) if s is not None else 0.0,
                    "box": b.tolist() if hasattr(b, "tolist") else b
                })

        extracted = ekstrak_informasi_kk(lines)
        extracted["total_lines_detected"] = len(lines)
        return extracted

    except Exception as e:
        logger.exception("Gagal memproses OCR Kartu Keluarga dengan PaddleOCR")
        return {
            "success": False,
            "error": f"Terjadi kesalahan saat memproses OCR: {str(e)}"
        }
    finally:
        for tmp in temp_files:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
