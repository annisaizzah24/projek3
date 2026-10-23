import datetime
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy.exc import IntegrityError
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
# 5. TAMBAH KELUARGA: GET / POST /keluarga/tambah (Flask-WTF)
# =============================================================================
@warga_bp.route("/keluarga/tambah", methods=["GET", "POST"])
@login_required
@role_required("admin", "petugas_verifikasi")
def tambah_keluarga():
    form = KeluargaForm()

    if form.validate_on_submit():
        try:
            keluarga_baru = Keluarga(
                nomor_kk=form.nomor_kk.data.strip(),
                kepala_keluarga=form.kepala_keluarga.data.strip(),
                alamat=form.alamat.data.strip()
            )
            db.session.add(keluarga_baru)
            db.session.commit()
            flash(f"Kartu Keluarga No. {keluarga_baru.nomor_kk} ({keluarga_baru.kepala_keluarga}) berhasil didaftarkan.", "success")
            return redirect(url_for("warga.daftar_warga"))
        except IntegrityError:
            db.session.rollback()
            form.nomor_kk.errors.append("Nomor KK sudah terdaftar dalam database.")
        except Exception as exc:
            db.session.rollback()
            flash(f"Gagal mendaftarkan keluarga: {str(exc)}", "danger")

    return render_template("warga/form_keluarga.html", form=form)
