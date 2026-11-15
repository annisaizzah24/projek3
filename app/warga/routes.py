import datetime
import json
import os
import re
import uuid
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash, jsonify, abort, send_file, current_app
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from app.warga import warga_bp
from app.models import Warga, Keluarga, Verifikasi, DESIL_INFO, get_desil_info
from app.extensions import db
from app.forms import WargaForm, KeluargaForm
from app.auth.routes import role_required
from app.desil.routes import simpan_berkas_unggah

# =============================================================================
# 1. DAFTAR WARGA: GET /warga (Search NIK/Nama & Filter Keluarga & Filter Desil)
# =============================================================================
@warga_bp.route("/warga", methods=["GET"])
@login_required
@role_required("admin", "petugas_verifikasi")
def daftar_warga():
    search = request.args.get("search", "").strip()
    id_keluarga = request.args.get("keluarga", "").strip() or request.args.get("id_keluarga", "").strip()
    desil_filter = request.args.get("desil", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(100, request.args.get("per_page", 10, type=int)))

    query = Warga.query.join(Keluarga, Warga.id_keluarga == Keluarga.id)

    if search:
        wildcard = f"%{search}%"
        query = query.filter(
            db.or_(
                Warga.nik.ilike(wildcard),
                Warga.nama.ilike(wildcard)
            )
        )

    if id_keluarga:
        if id_keluarga.isdigit() and len(id_keluarga) != 16:
            query = query.filter(Warga.id_keluarga == int(id_keluarga))
        else:
            query = query.filter(Keluarga.nomor_kk == id_keluarga)

    if desil_filter and desil_filter.isdigit():
        query = query.filter(Warga.desil == int(desil_filter))

    pagination = query.order_by(Warga.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    daftar_keluarga = Keluarga.query.order_by(Keluarga.nomor_kk.asc()).all()

    # Daftar dokumen KK yang diunggah warga (prioritaskan Menunggu Verifikasi & Perlu Perbaikan)
    dokumen_kk_list = Keluarga.query.filter(
        db.or_(
            Keluarga.dokumen_kk.isnot(None),
            Keluarga.status_dokumen != "Belum Diunggah"
        )
    ).order_by(
        db.case(
            (Keluarga.status_dokumen == "Menunggu Verifikasi", 1),
            (Keluarga.status_dokumen == "Perlu Perbaikan", 2),
            (Keluarga.status_dokumen == "Terverifikasi", 3),
            else_=4
        ),
        Keluarga.updated_at.desc()
    ).all()
    pending_kk_count = sum(1 for k in dokumen_kk_list if k.status_dokumen == "Menunggu Verifikasi")

    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        items = [{
            "id": w.id,
            "nik": w.nik,
            "nama": w.nama,
            "alamat": w.alamat,
            "nomor_kk": w.keluarga.nomor_kk if w.keluarga else None,
            "id_keluarga": w.id_keluarga,
            "penghasilan": float(w.penghasilan),
            "jumlah_tanggungan": w.jumlah_tanggungan,
            "nilai_aset": float(w.nilai_aset or 0.0),
            "desil": w.desil,
            "keterangan_desil": w.keterangan_desil,
            "foto_rumah": w.foto_rumah,
            "tanggal_lahir": w.tanggal_lahir.isoformat() if w.tanggal_lahir else None
        } for w in pagination.items]
        return jsonify({
            "success": True,
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
            "items": items
        })

    return render_template(
        "warga/index.html",
        pagination=pagination,
        daftar_keluarga=daftar_keluarga,
        dokumen_kk_list=dokumen_kk_list,
        pending_kk_count=pending_kk_count,
        search=search,
        selected_keluarga=id_keluarga,
        desil_filter=desil_filter,
        desil_info=DESIL_INFO
    )


# =============================================================================
# 2. TAMBAH WARGA: GET / POST /warga/tambah (Flask-WTF)
# =============================================================================
@warga_bp.route("/warga/tambah", methods=["GET", "POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def tambah_warga():
    form = WargaForm()

    if form.validate_on_submit():
        try:
            foto_rumah_path = None
            if form.foto_rumah.data:
                foto_rumah_path = simpan_berkas_unggah(form.foto_rumah.data, folder="rumah")

            foto_kendaraan_path = None
            if form.foto_kendaraan.data:
                foto_kendaraan_path = simpan_berkas_unggah(form.foto_kendaraan.data, folder="kendaraan")

            desil_val = form.desil.data if (form.desil.data and form.desil.data > 0) else None

            warga_baru = Warga(
                nik=form.nik.data.strip(),
                nama=form.nama.data.strip(),
                alamat=form.alamat.data.strip(),
                id_keluarga=form.id_keluarga.data,
                penghasilan=form.penghasilan.data,
                jumlah_tanggungan=form.jumlah_tanggungan.data or 0,
                status_rumah=form.status_rumah.data or "milik_sendiri",
                luas_tanah=float(form.luas_tanah.data) if form.luas_tanah.data is not None else 36.0,
                daya_listrik=form.daya_listrik.data or 450,
                jenis_kendaraan=form.jenis_kendaraan.data or "tidak_ada",
                jumlah_kendaraan=form.jumlah_kendaraan.data or 0,
                tanggal_lahir=form.tanggal_lahir.data,
                desil=desil_val,
                foto_rumah=foto_rumah_path,
                foto_kendaraan=foto_kendaraan_path
            )

            # Hitung estimasi aset otomatis jika nilai_aset kosong atau 0
            if form.nilai_aset.data and Decimal(str(form.nilai_aset.data)) > 0:
                warga_baru.nilai_aset = form.nilai_aset.data
            else:
                warga_baru.nilai_aset = warga_baru.hitung_estimasi_aset_otomatis()

            # Desil dihitung otomatis hanya jika seluruh data wajib termasuk foto rumah telah tersedia
            if foto_rumah_path:
                warga_baru.desil = warga_baru.hitung_desil_otomatis()
            else:
                warga_baru.desil = None

            db.session.add(warga_baru)
            db.session.commit()
            flash(f"Warga '{warga_baru.nama}' (NIK: {warga_baru.nik}) berhasil didaftarkan.", "success")
            return redirect(url_for("warga.daftar_warga"))
        except IntegrityError:
            db.session.rollback()
            form.nik.errors.append(f"NIK '{form.nik.data}' sudah terdaftar dalam sistem database.")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal menyimpan data warga: {str(exc)}", "danger")

    return render_template("warga/form_warga.html", form=form, is_edit=False)


# =============================================================================
# 3. EDIT WARGA: GET / POST /warga/<id>/edit (Flask-WTF)
# =============================================================================
@warga_bp.route("/warga/<int:id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def edit_warga(id):
    warga = db.get_or_404(Warga, id)
    form = WargaForm(current_warga_id=warga.id, obj=warga)

    if request.method == "GET":
        form.desil.data = warga.desil or 0
        form.status_rumah.data = warga.status_rumah or "milik_sendiri"
        if warga.luas_tanah is not None:
            val = float(warga.luas_tanah)
            form.luas_tanah.data = int(val) if val.is_integer() else val
        else:
            form.luas_tanah.data = 36
        form.daya_listrik.data = warga.daya_listrik or 450
        form.jenis_kendaraan.data = warga.jenis_kendaraan or "tidak_ada"
        form.jumlah_kendaraan.data = warga.jumlah_kendaraan or 0

    if form.validate_on_submit():
        try:
            warga.nik = form.nik.data.strip()
            warga.nama = form.nama.data.strip()
            warga.alamat = form.alamat.data.strip()
            warga.id_keluarga = form.id_keluarga.data
            warga.penghasilan = form.penghasilan.data
            warga.jumlah_tanggungan = form.jumlah_tanggungan.data or 0
            warga.status_rumah = form.status_rumah.data or "milik_sendiri"
            warga.luas_tanah = float(form.luas_tanah.data) if form.luas_tanah.data is not None else 36.0
            warga.daya_listrik = form.daya_listrik.data or 450
            warga.jenis_kendaraan = form.jenis_kendaraan.data or "tidak_ada"
            warga.jumlah_kendaraan = form.jumlah_kendaraan.data or 0
            warga.tanggal_lahir = form.tanggal_lahir.data

            # Hitung estimasi aset otomatis jika form.nilai_aset kosong atau 0
            if form.nilai_aset.data and Decimal(str(form.nilai_aset.data)) > 0:
                warga.nilai_aset = form.nilai_aset.data
            else:
                warga.nilai_aset = warga.hitung_estimasi_aset_otomatis()

            if form.foto_rumah.data:
                foto_path = simpan_berkas_unggah(form.foto_rumah.data, folder="rumah")
                if foto_path:
                    warga.foto_rumah = foto_path

            if form.foto_kendaraan.data:
                foto_k = simpan_berkas_unggah(form.foto_kendaraan.data, folder="kendaraan")
                if foto_k:
                    warga.foto_kendaraan = foto_k

            # Desil dihitung otomatis hanya jika seluruh data wajib termasuk foto rumah telah tersedia
            if warga.foto_rumah:
                warga.desil = warga.hitung_desil_otomatis()
            else:
                warga.desil = None

            db.session.commit()
            flash(f"Data warga '{warga.nama}' berhasil diperbarui.", "success")
            return redirect(url_for("warga.daftar_warga"))
        except IntegrityError:
            db.session.rollback()
            form.nik.errors.append("NIK sudah digunakan oleh warga lain.")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal memperbarui data: {str(exc)}", "danger")

    return render_template("warga/form_warga.html", form=form, warga=warga, is_edit=True)


# =============================================================================
# 6. API: POST /warga/api/hitung-desil (Real-time Calculation)
# =============================================================================
@warga_bp.route("/warga/api/hitung-desil", methods=["POST"])
@warga_bp.route("/api/hitung-desil", methods=["POST"])
@login_required
def api_hitung_desil():
    """
    API endpoint untuk menghitung estimasi desil secara real-time
    berdasarkan seluruh indikator parameter fisik, listrik, & pendapatan,
    dengan syarat mutlak foto rumah wajib telah diunggah.
    """
    data = request.get_json(silent=True) or request.form.to_dict()

    # 1. Validasi kelengkapan foto rumah (syarat wajib verifikasi fisik)
    has_foto = (
        data.get("has_foto") in (True, "true", "1", 1) 
        or bool(request.files.get("foto_rumah"))
        or data.get("has_existing_photo") in (True, "true", "1", 1)
    )

    if not has_foto:
        return jsonify({
            "success": True,
            "lengkap": False,
            "desil": None,
            "pesan": "Lengkapi seluruh data penghasilan, aset fisik, kelistrikan, dan unggah foto tampak depan rumah untuk menghitung Tingkat Desil Kesejahteraan."
        })

    # 2. Validasi penghasilan
    penghasilan_raw = data.get("penghasilan")
    if penghasilan_raw is None or str(penghasilan_raw).strip() == "":
        return jsonify({
            "success": True,
            "lengkap": False,
            "desil": None,
            "pesan": "Lengkapi seluruh data penghasilan, aset fisik, kelistrikan, dan unggah foto tampak depan rumah untuk menghitung Tingkat Desil Kesejahteraan."
        })

    try:
        penghasilan = float(penghasilan_raw)
        if penghasilan < 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "lengkap": False,
            "desil": None,
            "pesan": "Format penghasilan tidak valid (harus bernilai angka >= 0)."
        }), 400

    # 3. Validasi parameter aset fisik & kelistrikan
    luas_raw = data.get("luas_tanah")
    if luas_raw is None or str(luas_raw).strip() == "":
        return jsonify({
            "success": True,
            "lengkap": False,
            "desil": None,
            "pesan": "Luas bangunan atau tanah tempat tinggal wajib diisi."
        })

    try:
        luas_tanah = float(luas_raw)
        if luas_tanah <= 0:
            return jsonify({
                "success": True,
                "lengkap": False,
                "desil": None,
                "pesan": "Luas bangunan atau tanah tempat tinggal harus lebih dari 0 m²."
            })
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "lengkap": False,
            "desil": None,
            "pesan": "Format luas bangunan/tanah tidak valid."
        }), 400

    status_rumah = data.get("status_rumah")
    if not status_rumah or str(status_rumah).strip() == "":
        return jsonify({
            "success": True,
            "lengkap": False,
            "desil": None,
            "pesan": "Status kepemilikan bangunan tempat tinggal wajib dipilih."
        })

    daya_raw = data.get("daya_listrik")
    if daya_raw is None or str(daya_raw).strip() == "":
        return jsonify({
            "success": True,
            "lengkap": False,
            "desil": None,
            "pesan": "Parameter meteran listrik atau daya PLN wajib dipilih."
        })
    try:
        daya_listrik = int(daya_raw)
    except (ValueError, TypeError):
        daya_listrik = 450

    jenis_kendaraan = data.get("jenis_kendaraan")
    if not jenis_kendaraan or str(jenis_kendaraan).strip() == "":
        return jsonify({
            "success": True,
            "lengkap": False,
            "desil": None,
            "pesan": "Jenis kepemilikan kendaraan wajib dipilih."
        })

    tanggungan = data.get("jumlah_tanggungan", 0)
    jumlah_kendaraan = data.get("jumlah_kendaraan", 0)
    nilai_aset = data.get("nilai_aset", 0)

    hasil = Warga.kalkulasi_desil_lengkap(
        penghasilan=penghasilan,
        jumlah_tanggungan=tanggungan,
        status_rumah=status_rumah,
        luas_tanah=luas_tanah,
        daya_listrik=daya_listrik,
        jenis_kendaraan=jenis_kendaraan,
        jumlah_kendaraan=jumlah_kendaraan,
        nilai_aset=nilai_aset
    )

    dummy_w = Warga(
        status_rumah=status_rumah,
        luas_tanah=luas_tanah,
        jenis_kendaraan=jenis_kendaraan,
        jumlah_kendaraan=jumlah_kendaraan
    )
    estimasi_aset = float(dummy_w.hitung_estimasi_aset_otomatis())

    return jsonify({
        "success": True,
        "lengkap": True,
        "estimasi_aset": estimasi_aset,
        **hasil
    })


# =============================================================================
# 4. HAPUS WARGA: POST /warga/<id>/hapus (Protected via ON DELETE RESTRICT)
# =============================================================================
@warga_bp.route("/warga/<int:id>/hapus", methods=["POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def hapus_warga(id):
    warga = db.get_or_404(Warga, id)

    verif_count = Verifikasi.query.filter_by(id_warga=warga.id).count()
    if verif_count > 0:
        flash(
            f"Warga '{warga.nama}' tidak dapat dihapus karena memiliki {verif_count} data historis verifikasi bantuan sosial.",
            "danger"
        )
        return redirect(url_for("warga.daftar_warga"))

    try:
        nama = warga.nama
        db.session.delete(warga)
        db.session.commit()
        flash(f"Warga '{nama}' berhasil dihapus dari sistem.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Gagal menghapus warga: Terdapat relasi data lain yang masih terikat.", "danger")
    except Exception as exc:
        db.session.rollback()
        flash(f"Gagal menghapus warga: {str(exc)}", "danger")

    return redirect(url_for("warga.daftar_warga"))


# =============================================================================
# 5. UNGGAH & VERIFIKASI DOKUMEN KARTU KELUARGA (SELF-SERVICE WARGA)
# =============================================================================
UPLOAD_DIR = "uploads/temp"
KK_STORAGE_DIR = "uploads/kk"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(KK_STORAGE_DIR, exist_ok=True)

ALLOWED_KK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_KK_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _validate_kk_file(file_storage):
    """Validasi tipe berkas (JPG/JPEG/PNG/PDF), header magic bytes, dan ukuran maksimal 10 MB."""
    if not file_storage or not getattr(file_storage, "filename", ""):
        return False, "Berkas dokumen Kartu Keluarga wajib dipilih.", ""

    ext = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    if ext not in ALLOWED_KK_EXTENSIONS:
        return False, "Format file tidak didukung. Gunakan JPG, JPEG, PNG, atau PDF.", ""

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size <= 0:
        return False, "Berkas yang diunggah kosong.", ""
    if size > MAX_KK_FILE_SIZE:
        return False, "Ukuran berkas melebihi batas maksimal 10 MB.", ""

    header = file_storage.stream.read(8)
    file_storage.stream.seek(0)
    if ext in (".jpg", ".jpeg") and not header.startswith(b"\xff\xd8\xff"):
        return False, "Isi berkas tidak valid sebagai gambar JPG/JPEG.", ""
    if ext == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "Isi berkas tidak valid sebagai gambar PNG.", ""
    if ext == ".pdf" and not header.startswith(b"%PDF"):
        return False, "Isi berkas tidak valid sebagai dokumen PDF.", ""

    return True, "", ext


@warga_bp.route("/keluarga/tambah", methods=["GET", "POST"])
@login_required
def tambah_keluarga():
    """Rute lama + Kartu Keluarga: diarahkan ke Akun User (warga) atau Data Warga (admin)."""
    if current_user.is_warga:
        return redirect(url_for("dashboard") + "#dokumen-kk")
    flash("Fitur unggah & pendaftaran Kartu Keluarga kini dilakukan secara mandiri oleh warga melalui Akun User.", "info")
    return redirect(url_for("warga.daftar_warga"))


@warga_bp.route("/akun/kk/simpan", methods=["POST"])
@login_required
@role_required("warga")
def simpan_kk_warga():
    """Menyimpan dokumen KK (JPG/PNG/PDF) dan data keluarga milik akun warga yang sedang login."""
    nomor_kk = (request.form.get("nomor_kk") or "").strip()
    kepala_keluarga = (request.form.get("kepala_keluarga") or "").strip()
    alamat = (request.form.get("alamat") or "").strip()
    rt_rw = (request.form.get("rt_rw") or "").strip()
    desa_kelurahan = (request.form.get("desa_kelurahan") or "").strip()
    kecamatan = (request.form.get("kecamatan") or "").strip()
    kabupaten_kota = (request.form.get("kabupaten_kota") or "").strip()
    provinsi = (request.form.get("provinsi") or "").strip()

    if not re.match(r"^\d{16}$", nomor_kk):
        return jsonify({"success": False, "error": "Nomor KK harus tepat 16 digit angka numerik."}), 400
    if not kepala_keluarga:
        return jsonify({"success": False, "error": "Nama Kepala Keluarga wajib diisi."}), 400
    if not alamat:
        return jsonify({"success": False, "error": "Alamat domisili wajib diisi."}), 400

    # Identifikasi apakah akun ini sudah memiliki record Keluarga
    existing_kk = current_user.data_keluarga
    warga_terkait = current_user.data_warga

    # Cek duplikasi Nomor KK terhadap keluarga milik akun/warga lain
    dup_kk = Keluarga.query.filter_by(nomor_kk=nomor_kk).first()
    if dup_kk:
        if existing_kk and dup_kk.id != existing_kk.id:
            return jsonify({"success": False, "error": f"Nomor KK '{nomor_kk}' sudah terdaftar pada keluarga lain. Duplikasi data KK tidak diperbolehkan."}), 400
        if not existing_kk:
            if dup_kk.id_user is not None and dup_kk.id_user != current_user.id:
                return jsonify({"success": False, "error": f"Nomor KK '{nomor_kk}' sudah terdaftar oleh akun warga lain."}), 400
            if dup_kk.id_user is None:
                # Izinkan klaim hanya jika warga_terkait memang anggota keluarga tersebut
                if not (warga_terkait and warga_terkait.id_keluarga == dup_kk.id):
                    return jsonify({"success": False, "error": f"Nomor KK '{nomor_kk}' sudah terdaftar dalam sistem. Silakan hubungi admin jika nomor KK tersebut milik keluarga Anda."}), 400
                existing_kk = dup_kk

    file = request.files.get("dokumen_kk")
    has_new_file = bool(file and getattr(file, "filename", ""))
    saved_rel_path = existing_kk.dokumen_kk if existing_kk else None

    if not has_new_file and not saved_rel_path:
        return jsonify({"success": False, "error": "Silakan unggah berkas dokumen Kartu Keluarga (JPG, JPEG, PNG, atau PDF)."}), 400

    if has_new_file:
        ok, err_msg, ext = _validate_kk_file(file)
        if not ok:
            return jsonify({"success": False, "error": err_msg}), 400
        proj_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
        kk_dir = os.path.join(proj_root, KK_STORAGE_DIR)
        os.makedirs(kk_dir, exist_ok=True)
        unique_name = f"kk_u{current_user.id}_{uuid.uuid4().hex[:12]}{ext}"
        dest_abs = os.path.join(kk_dir, unique_name)
        file.save(dest_abs)
        saved_rel_path = f"uploads/kk/{unique_name}"

    try:
        if existing_kk:
            riwayat = list(existing_kk.riwayat_dokumen or [])
            # Arsipkan riwayat dokumen/verifikasi sebelumnya tanpa menghilangkan jejak audit
            if existing_kk.dokumen_kk or existing_kk.status_dokumen != "Belum Diunggah":
                riwayat.append({
                    "aksi": "Pembaruan Dokumen KK oleh Warga",
                    "nomor_kk": existing_kk.nomor_kk,
                    "dokumen_kk": existing_kk.dokumen_kk,
                    "status_sebelumnya": existing_kk.status_dokumen,
                    "catatan_sebelumnya": existing_kk.catatan_verifikasi,
                    "tanggal_verifikasi_sebelumnya": existing_kk.tanggal_verifikasi_dokumen.isoformat() if existing_kk.tanggal_verifikasi_dokumen else None,
                    "waktu": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

            existing_kk.nomor_kk = nomor_kk
            existing_kk.kepala_keluarga = kepala_keluarga
            existing_kk.alamat = alamat
            existing_kk.rt_rw = rt_rw or None
            existing_kk.desa_kelurahan = desa_kelurahan or None
            existing_kk.kecamatan = kecamatan or None
            existing_kk.kabupaten_kota = kabupaten_kota or None
            existing_kk.provinsi = provinsi or None
            existing_kk.id_user = current_user.id
            existing_kk.dokumen_kk = saved_rel_path
            existing_kk.hasil_ocr_kk = None
            existing_kk.status_dokumen = "Menunggu Verifikasi"
            existing_kk.catatan_verifikasi = None
            existing_kk.riwayat_dokumen = riwayat
            keluarga_obj = existing_kk
        else:
            keluarga_obj = Keluarga(
                nomor_kk=nomor_kk,
                kepala_keluarga=kepala_keluarga,
                alamat=alamat,
                rt_rw=rt_rw or None,
                desa_kelurahan=desa_kelurahan or None,
                kecamatan=kecamatan or None,
                kabupaten_kota=kabupaten_kota or None,
                provinsi=provinsi or None,
                id_user=current_user.id,
                dokumen_kk=saved_rel_path,
                hasil_ocr_kk=None,
                status_dokumen="Menunggu Verifikasi",
                riwayat_dokumen=[{
                    "aksi": "Unggahan Pertama Dokumen KK oleh Warga",
                    "nomor_kk": nomor_kk,
                    "dokumen_kk": saved_rel_path,
                    "status": "Menunggu Verifikasi",
                    "waktu": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }]
            )
            db.session.add(keluarga_obj)

        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Dokumen dan data Kartu Keluarga berhasil disimpan dan dikirim untuk verifikasi Admin.",
            "keluarga_id": keluarga_obj.id,
            "status_dokumen": keluarga_obj.status_dokumen,
            "dokumen_url": url_for("warga.lihat_dokumen_kk", keluarga_id=keluarga_obj.id)
        })
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Nomor KK '{nomor_kk}' sudah terdaftar dalam database."}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Gagal menyimpan data KK: {exc}"}), 500


@warga_bp.route("/keluarga/dokumen/<int:keluarga_id>", methods=["GET"])
@login_required
def lihat_dokumen_kk(keluarga_id):
    """Menampilkan file dokumen KK dengan pembatasan akses ketat per akun pemilik/admin."""
    keluarga = db.get_or_404(Keluarga, keluarga_id)

    # Kontrol Akses: Admin/Petugas boleh akses, Warga hanya boleh akses KK miliknya sendiri
    if not current_user.is_warga:
        pass  # Admin / petugas_verifikasi diizinkan
    else:
        warga_terkait = current_user.data_warga
        is_owner = (keluarga.id_user == current_user.id)
        is_member = bool(warga_terkait and warga_terkait.id_keluarga == keluarga.id)
        if not (is_owner or is_member):
            abort(403)

    if not keluarga.dokumen_kk:
        abort(404)

    proj_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    abs_path = os.path.abspath(os.path.join(proj_root, keluarga.dokumen_kk))
    kk_root = os.path.abspath(os.path.join(proj_root, KK_STORAGE_DIR))
    if not abs_path.startswith(kk_root) or not os.path.exists(abs_path):
        abort(404)

    return send_file(abs_path, as_attachment=False)


@warga_bp.route("/keluarga/<int:keluarga_id>/verifikasi-dokumen", methods=["POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def verifikasi_dokumen_kk(keluarga_id):
    """Endpoint Admin/Petugas untuk memverifikasi dokumen KK yang diunggah warga."""
    keluarga = db.get_or_404(Keluarga, keluarga_id)
    aksi = (request.form.get("aksi") or "").strip().lower()
    catatan = (request.form.get("catatan_verifikasi") or "").strip()

    if aksi == "terverifikasi":
        status_baru = "Terverifikasi"
    elif aksi == "perlu_perbaikan":
        status_baru = "Perlu Perbaikan"
        if not catatan:
            catatan = "Dokumen atau data Kartu Keluarga kurang jelas/tidak sesuai. Silakan unggah ulang atau perbaiki data."
    else:
        flash("Status verifikasi dokumen KK tidak valid.", "danger")
        return redirect(url_for("warga.daftar_warga"))

    now_dt = datetime.datetime.now()
    riwayat = list(keluarga.riwayat_dokumen or [])
    riwayat.append({
        "aksi": f"Verifikasi Admin: {status_baru}",
        "petugas": current_user.nama,
        "status": status_baru,
        "catatan": catatan,
        "waktu": now_dt.strftime("%Y-%m-%d %H:%M:%S")
    })

    keluarga.status_dokumen = status_baru
    keluarga.catatan_verifikasi = catatan or None
    keluarga.id_petugas_verifikasi = current_user.id
    keluarga.tanggal_verifikasi_dokumen = now_dt
    keluarga.riwayat_dokumen = riwayat

    db.session.commit()
    flash(f"Dokumen KK No. {keluarga.nomor_kk} ({keluarga.kepala_keluarga}) ditandai sebagai '{status_baru}'.", "success")
    return redirect(url_for("warga.daftar_warga"))
