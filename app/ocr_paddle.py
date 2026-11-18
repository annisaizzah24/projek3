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
            # 100% berada di 33% teratas dokumen KK. Memotong 67% area bawah menghemat waktu secara drastis pada CPU.
            crop_h = int(h * 0.33)
            im = im.crop((0, 0, w, crop_h))
            w, h = im.size
            modified = True

            # 3. Downscale jika resolusi foto sangat besar (> 1200px) untuk kecepatan inferensi CPU
            MAX_DIM = 1200
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
    raw_texts = [item.get("text", "").strip() for item in lines if item.get("text", "").strip()]
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
    for line in raw_texts:
        m = re.search(r"(?:no|nomor)?\.?\s*[:.\-]?\s*(\d{16})", line, re.IGNORECASE)
        if m:
            hasil["nomor_kk"] = m.group(1)
            break

    if not hasil["nomor_kk"]:
        for line in raw_texts:
            m = re.search(r"\b(\d{16})\b", line)
            if m:
                hasil["nomor_kk"] = m.group(1)
                break

    # 2. Scanning Label Berurutan (Header KK Format Standar)
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
                if not re.search(r"^(?:kabupaten|keluapteian|keuapteian|provinsi)", cand, re.I):
                    hasil["kecamatan"] = cand
            elif i + 1 < len(raw_texts):
                for offset in (1, 2, 3, 4, 5, 6, 7):
                    if i + offset < len(raw_texts):
                        cand = clean_val(raw_texts[i + offset])
                        if cand and len(cand) >= 3 and not re.search(r"\d", cand) and not re.search(r"^(?:kode|pos|kabupaten|keluapteian|keuapteian|provinsi|proroisi|desa|kelurahan|alamat|rt|jl)", cand, re.I):
                            hasil["kecamatan"] = cand
                            break

        # F. Kabupaten / Kota
        if not hasil["kabupaten_kota"] and re.search(r"^(?:kabupaten\s*[/.]?\s*kota|keluapteian/kota|keuapteian/kota)", l_lower):
            m = re.search(r"^(?:kabupaten\s*[/.]?\s*kota|keluapteian/kota|keuapteian/kota)\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"^(?:provinsi|prooisi|proroisi)", cand, re.I):
                    hasil["kabupaten_kota"] = cand
            elif i + 1 < len(raw_texts):
                for offset in (1, 2):
                    if i + offset < len(raw_texts):
                        cand = clean_val(raw_texts[i + offset])
                        if cand and not re.search(r"^(?:provinsi|prooisi|proroisi|kode|pos)", cand, re.I):
                            hasil["kabupaten_kota"] = cand
                            break

        # G. Provinsi
        if not hasil["provinsi"] and re.search(r"^(?:provinsi|prooisi|proisi|proroisi)", l_lower):
            m = re.search(r"^(?:provinsi|prooisi|proisi|proroisi)\s*[:.\-]?\s*(.*)", l_strip, re.IGNORECASE)
            if m and clean_val(m.group(1)):
                cand = clean_val(m.group(1))
                if not re.search(r"^(?:no|nama|nik)", cand, re.I):
                    hasil["provinsi"] = cand
            elif i + 1 < len(raw_texts):
                cand = clean_val(raw_texts[i + 1])
                if cand and not re.search(r"^(?:no|nama|nik)", cand, re.I):
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
            m_rtrw = re.search(r"\b([0-9OoSs]{1,4}\s*[/]\s*[0-9OoSs\-]{1,4})\b", l)
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

    # 6. NIK Kepala Keluarga: 15-16 digit angka selain nomor KK (biasanya di baris pertama tabel anggota)
    for line in raw_texts:
        m_nik = re.search(r"(\d{15,16})", line)
        if m_nik:
            val = m_nik.group(1)
            if val != hasil["nomor_kk"]:
                hasil["nik_kepala_keluarga"] = val
                break

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
