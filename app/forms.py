import re
import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, PasswordField, TextAreaField, DecimalField, 
    IntegerField, DateField, SelectField, SubmitField
)
from wtforms.validators import DataRequired, Length, Regexp, NumberRange, Optional, ValidationError, EqualTo
from app.models import Warga, Keluarga, User, DESIL_INFO


class LoginForm(FlaskForm):
    """Form autentikasi login pengguna."""
    username = StringField(
        "Username",
        validators=[DataRequired(message="Username wajib diisi."), Length(min=3, max=50)]
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password wajib diisi.")]
    )
    submit = SubmitField("Masuk ke Sistem")


class KeluargaForm(FlaskForm):
    """Form pendaftaran Kartu Keluarga (KK)."""
    nomor_kk = StringField(
        "Nomor Kartu Keluarga (KK)",
        validators=[
            DataRequired(message="Nomor KK wajib diisi."),
            Regexp(r"^\d{16}$", message="Nomor KK harus tepat 16 digit angka numerik.")
        ]
    )
    kepala_keluarga = StringField(
        "Nama Kepala Keluarga",
        validators=[DataRequired(message="Nama kepala keluarga wajib diisi.")]
    )
    alamat = TextAreaField(
        "Alamat Domisili Keluarga",
        validators=[DataRequired(message="Alamat domisili keluarga wajib diisi.")]
    )
    submit = SubmitField("Simpan Kartu Keluarga")

    def validate_nomor_kk(self, field):
        existing = Keluarga.query.filter_by(nomor_kk=field.data.strip()).first()
        if existing:
            raise ValidationError(f"Nomor KK '{field.data}' sudah terdaftar dalam sistem.")


class WargaForm(FlaskForm):
    """Form tambah & edit data warga."""
    nik = StringField(
        "Nomor Induk Kependudukan (NIK)",
        validators=[
            DataRequired(message="NIK wajib diisi."),
            Regexp(r"^\d{16}$", message="NIK harus tepat 16 digit angka numerik.")
        ]
    )
    id_keluarga = SelectField(
        "Kartu Keluarga (KK)",
        coerce=int,
        validators=[DataRequired(message="Pilih Kartu Keluarga.")]
    )
    nama = StringField(
        "Nama Lengkap Sesuai KTP",
        validators=[DataRequired(message="Nama lengkap warga wajib diisi.")]
    )
    alamat = TextAreaField(
        "Alamat Domisili Lengkap",
        validators=[DataRequired(message="Alamat domisili wajib diisi.")]
    )
    tanggal_lahir = DateField(
        "Tanggal Lahir",
        format="%Y-%m-%d",
        validators=[DataRequired(message="Tanggal lahir wajib diisi.")]
    )
    penghasilan = DecimalField(
        "Penghasilan Bulanan (Rp)",
        places=2,
        validators=[
            DataRequired(message="Penghasilan wajib diisi."),
            NumberRange(min=0, message="Penghasilan tidak boleh bernilai negatif (>= 0).")
        ]
    )
    jumlah_tanggungan = IntegerField(
        "Jumlah Tanggungan (Orang)",
        default=0,
        validators=[
            NumberRange(min=0, message="Jumlah tanggungan tidak boleh bernilai negatif (>= 0).")
        ]
    )
    nilai_aset = DecimalField(
        "Estimasi Total Nilai Aset (Rp)",
        places=2,
        default=0.0,
        validators=[
            Optional(),
            NumberRange(min=0, message="Nilai aset tidak boleh bernilai negatif (>= 0).")
        ]
    )
    # Rincian Parameter Aset Fisik & Infrastruktur (Revisi Dosen)
    status_rumah = SelectField(
        "Status Kepemilikan Rumah Tinggal",
        choices=[
            ("milik_sendiri", "Milik Sendiri (Dihitung Sebagai Aset Penuh)"),
            ("sewa_kontrak", "Sewa / Kontrak (Bukan Aset Milik Sendiri)"),
            ("menumpang", "Menumpang / Milik Kerabat / Bebas Sewa")
        ],
        default="milik_sendiri"
    )
    luas_tanah = DecimalField(
        "Luas Bangunan (m²)",
        places=2,
        default=36,
        validators=[
            DataRequired(message="Luas bangunan wajib diisi."),
            NumberRange(min=0.01, message="Luas bangunan harus berupa angka positif lebih dari 0 m².")
        ]
    )
    daya_listrik = SelectField(
        "Parameter Meteran Listrik (Daya PLN)",
        coerce=int,
        choices=[
            (450, "450 VA (Bersubsidi — Indikator Kemiskinan Ekstrem)"),
            (900, "900 VA (Bersubsidi / Prasejahtera)"),
            (1300, "1.300 VA (Non-Subsidi / Golongan Menengah)"),
            (2200, "2.200 VA ke atas (Golongan Mampu / Mandiri)"),
            (0, "Non-PLN / Menumpang Tetangga")
        ],
        default=450
    )
    jenis_kendaraan = SelectField(
        "Kepemilikan Kendaraan",
        choices=[
            ("tidak_ada", "Tidak Memiliki Kendaraan"),
            ("motor", "Sepeda Motor"),
            ("mobil", "Mobil Pribadi"),
            ("motor_dan_mobil", "Sepeda Motor & Mobil")
        ],
        default="tidak_ada"
    )
    jumlah_kendaraan = IntegerField(
        "Jumlah Unit Kendaraan yang Dimiliki",
        default=0,
        validators=[
            Optional(),
            NumberRange(min=0, message="Jumlah unit kendaraan minimal 0 unit.")
        ]
    )
    foto_kendaraan = FileField(
        "Foto Bukti Kendaraan (Opsional)",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], message="Format file harus JPG, PNG, atau WEBP.")
        ]
    )
    desil = SelectField(
        "Tingkat Desil Kesejahteraan (1-10)",
        coerce=int,
        choices=[(0, "-- Otomatis Dihitung Sistem --")] + [
            (i, f"Desil {i} — {DESIL_INFO[i]['kategori']}") 
            for i in range(1, 11)
        ],
        default=0,
        validators=[Optional()]
    )
    foto_rumah = FileField(
        "Foto Tampak Depan Rumah (Wajib)",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], message="Format file harus JPG, JPEG, PNG, atau WEBP.")
        ]
    )
    submit = SubmitField("Simpan Data Warga")

    def __init__(self, current_warga_id=None, *args, **kwargs):
        super(WargaForm, self).__init__(*args, **kwargs)
        self.current_warga_id = current_warga_id
        self.id_keluarga.choices = [(0, "-- Pilih Kartu Keluarga --")] + [
            (k.id, f"{k.nomor_kk} — {k.kepala_keluarga}") 
            for k in Keluarga.query.order_by(Keluarga.nomor_kk.asc()).all()
        ]

    def validate_nik(self, field):
        query = Warga.query.filter_by(nik=field.data.strip())
        if self.current_warga_id:
            query = query.filter(Warga.id != self.current_warga_id)
        if query.first():
            raise ValidationError(f"NIK '{field.data}' sudah terdaftar dalam sistem.")

    def validate_tanggal_lahir(self, field):
        if field.data and field.data > datetime.date.today():
            raise ValidationError("Tanggal lahir tidak boleh berada di masa depan.")


class ProgramForm(FlaskForm):
    """Form master program bantuan sosial."""
    nama_program = StringField(
        "Nama Program Bantuan",
        validators=[DataRequired(message="Nama program bantuan wajib diisi.")]
    )
    kriteria_penghasilan_max = DecimalField(
        "Batas Maks. Penghasilan (Rp)",
        places=2,
        validators=[
            DataRequired(message="Batas penghasilan maksimal wajib diisi."),
            NumberRange(min=0, message="Batas penghasilan tidak boleh negatif.")
        ]
    )
    kriteria_tanggungan_min = IntegerField(
        "Syarat Min. Tanggungan (Orang)",
        default=0,
        validators=[
            NumberRange(min=0, message="Syarat minimal tanggungan tidak boleh negatif.")
        ]
    )
    kriteria_aset_max = DecimalField(
        "Batas Maks. Nilai Aset (Rp)",
        places=2,
        validators=[
            Optional(),
            NumberRange(min=0, message="Batas aset maksimal tidak boleh negatif.")
        ]
    )
    kriteria_desil_max = SelectField(
        "Batas Maksimal Kategori Desil",
        coerce=int,
        choices=[(0, "-- Tanpa Batasan Desil --")] + [
            (i, f"Maksimal Desil {i} ({DESIL_INFO[i]['kategori']})")
            for i in range(1, 11)
        ],
        default=4,
        validators=[Optional()]
    )
    deskripsi = TextAreaField("Deskripsi Program", validators=[Optional()])
    submit = SubmitField("Simpan Program")


class MulaiVerifikasiForm(FlaskForm):
    """Form pemilihan warga dan program untuk eksekusi evaluasi verifikasi."""
    id_warga = SelectField(
        "Pilih Warga Calon Penerima",
        coerce=int,
        validators=[DataRequired(message="Pilih warga calon penerima.")]
    )
    id_program = SelectField(
        "Pilih Program Bantuan",
        coerce=int,
        validators=[DataRequired(message="Pilih program bantuan.")]
    )
    catatan = TextAreaField("Catatan Awal Petugas (Opsional)", validators=[Optional()])
    submit = SubmitField("Jalankan Verifikasi")

    def __init__(self, *args, **kwargs):
        super(MulaiVerifikasiForm, self).__init__(*args, **kwargs)
        from app.models import ProgramBantuan
        self.id_warga.choices = [(0, "-- Pilih Warga Calon Penerima --")] + [
            (w.id, f"{w.nama} (NIK: {w.nik}) — Desil: {w.desil or 'Auto'} — Penghasilan: Rp {float(w.penghasilan):,.2f}") 
            for w in Warga.query.order_by(Warga.nama.asc()).all()
        ]
        self.id_program.choices = [(0, "-- Pilih Program Bantuan --")] + [
            (p.id, f"{p.nama_program} (Maks Desil: {p.kriteria_desil_max or 'Bebas'}, Maks Gaji: Rp {float(p.kriteria_penghasilan_max):,.2f})") 
            for p in ProgramBantuan.query.filter_by(is_active=True).order_by(ProgramBantuan.nama_program.asc()).all()
        ]


class KonfirmasiForm(FlaskForm):
    """Form pengesahan dan konfirmasi hasil verifikasi oleh petugas."""
    status_final = SelectField(
        "Tetapkan Status Final",
        choices=[
            ("", "-- Pilih Keputusan Final --"),
            ("layak", "Layak (Disetujui Menerima Bantuan)"),
            ("tidak_layak", "Tidak Layak (Ditolak)"),
            ("perlu_ditinjau", "Perlu Ditinjau (Butuh Survei Faktual)")
        ],
        validators=[DataRequired(message="Pilih status keputusan final.")]
    )
    catatan_petugas = TextAreaField(
        "Catatan Pengesahan Petugas",
        validators=[DataRequired(message="Catatan konfirmasi petugas wajib diisi.")]
    )
    submit = SubmitField("Sahkan Keputusan Final")


class PetugasForm(FlaskForm):
    """Form pendaftaran akun petugas atau administrator."""
    nama = StringField(
        "Nama Lengkap",
        validators=[DataRequired(message="Nama lengkap wajib diisi.")]
    )
    username = StringField(
        "Username",
        validators=[DataRequired(message="Username wajib diisi."), Length(min=3, max=50)]
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password wajib diisi."), Length(min=6, message="Password minimal 6 karakter.")]
    )
    role = SelectField(
        "Peran / Hak Akses (Role)",
        choices=[
            ("petugas_verifikasi", "Petugas Verifikasi"),
            ("admin", "Administrator Sistem")
        ],
        validators=[DataRequired(message="Pilih role.")]
    )
    submit = SubmitField("Simpan Akun")

    def validate_username(self, field):
        if User.query.filter_by(username=field.data.strip()).first():
            raise ValidationError(f"Username '{field.data}' sudah terdaftar dalam sistem.")


class EditPetugasForm(FlaskForm):
    """Form pengubahan data akun petugas atau administrator oleh Administrator."""
    nama = StringField(
        "Nama Lengkap",
        validators=[DataRequired(message="Nama lengkap wajib diisi.")]
    )
    username = StringField(
        "Username",
        validators=[DataRequired(message="Username wajib diisi."), Length(min=3, max=50)]
    )
    password = PasswordField(
        "Password Baru (Kosongkan jika tidak ingin mengubah)",
        validators=[Optional(), Length(min=6, message="Password minimal 6 karakter jika diisi.")]
    )
    role = SelectField(
        "Peran / Hak Akses (Role)",
        choices=[
            ("petugas_verifikasi", "Petugas Verifikasi"),
            ("admin", "Administrator Sistem")
        ],
        validators=[DataRequired(message="Pilih role.")]
    )
    submit = SubmitField("Simpan Perubahan")

    def __init__(self, current_user_id=None, *args, **kwargs):
        super(EditPetugasForm, self).__init__(*args, **kwargs)
        self.current_user_id = current_user_id

    def validate_username(self, field):
        query = User.query.filter_by(username=field.data.strip())
        if self.current_user_id:
            query = query.filter(User.id != self.current_user_id)
        if query.first():
            raise ValidationError(f"Username '{field.data}' sudah terdaftar dalam sistem.")


class RegisterForm(FlaskForm):
    """Form registrasi mandiri akun warga atau pengguna publik."""
    nama = StringField(
        "Nama Lengkap (Sesuai KTP)",
        validators=[DataRequired(message="Nama lengkap wajib diisi.")]
    )
    nik = StringField(
        "Nomor Induk Kependudukan (NIK)",
        validators=[
            Optional(),
            Regexp(r"^\d{16}$", message="NIK harus tepat 16 digit angka numerik jika diisi.")
        ]
    )
    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username wajib diisi."),
            Length(min=3, max=50, message="Username minimal 3 karakter dan maksimal 50 karakter.")
        ]
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password wajib diisi."),
            Length(min=6, message="Password minimal 6 karakter.")
        ]
    )
    konfirmasi_password = PasswordField(
        "Konfirmasi Password",
        validators=[
            DataRequired(message="Konfirmasi password wajib diisi."),
            EqualTo("password", message="Konfirmasi password tidak cocok dengan password yang dimasukkan.")
        ]
    )
    submit = SubmitField("Daftar Akun Warga")

    def validate_username(self, field):
        if User.query.filter_by(username=field.data.strip()).first():
            raise ValidationError(f"Username '{field.data}' sudah digunakan, silakan gunakan username lain.")

    def validate_nik(self, field):
        if field.data and field.data.strip():
            nik_val = field.data.strip()
            if User.query.filter_by(nik=nik_val).first():
                raise ValidationError(f"NIK '{nik_val}' sudah tertaut dengan akun warga lain.")


# =============================================================================
# FORMS: PENGAJUAN PERUBAHAN DESIL
# =============================================================================
class PengajuanPerubahanDesilForm(FlaskForm):
    """Form pengajuan permohonan perubahan desil oleh warga yang merasa desilnya keliru."""
    desil_diajukan = SelectField(
        "Desil yang Diajukan (Berdasarkan Kondisi Riil Kemiskinan)",
        coerce=int,
        choices=[
            (1, "Desil 1 — Sangat Miskin (Kemiskinan Ekstrem)"),
            (2, "Desil 2 — Miskin"),
            (3, "Desil 3 — Hampir Miskin"),
            (4, "Desil 4 — Rentan Miskin"),
            (5, "Desil 5 — Menengah Bawah"),
        ],
        validators=[DataRequired(message="Pilih desil yang diajukan.")]
    )
    penghasilan_terkini = DecimalField(
        "Gaji / Penghasilan Bulanan Riil Terkini (Rp)",
        places=2,
        validators=[
            DataRequired(message="Penghasilan bulanan riil wajib diisi."),
            NumberRange(min=0, message="Penghasilan tidak boleh bernilai negatif.")
        ]
    )
    jumlah_tanggungan = IntegerField(
        "Jumlah Tanggungan Keluarga Terkini (Orang)",
        default=0,
        validators=[
            NumberRange(min=0, message="Jumlah tanggungan tidak boleh bernilai negatif.")
        ]
    )
    foto_rumah = FileField(
        "Foto Tampak Depan Rumah / Tempat Tinggal",
        validators=[
            FileRequired(message="Foto fisik rumah wajib diunggah sebagai bukti kondisi ekonomi nyata."),
            FileAllowed(["jpg", "jpeg", "png", "webp"], message="Format foto harus berupa JPG, PNG, atau WEBP.")
        ]
    )
    dokumen_pendukung = FileField(
        "Dokumen Pendukung (Opsional: SKTM / Slip Gaji / Foto Dalam Rumah)",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp", "pdf"], message="Format berkas harus JPG, PNG, atau PDF.")
        ]
    )
    alasan_pengajuan = TextAreaField(
        "Alasan Pengajuan Perubahan Desil",
        validators=[
            DataRequired(message="Jelaskan alasan pengajuan secara rinci."),
            Length(min=15, message="Alasan pengajuan minimal 15 karakter agar dapat dipertimbangkan oleh petugas.")
        ]
    )
    submit = SubmitField("Kirim Pengajuan Perubahan Desil")


class ReviewPengajuanDesilForm(FlaskForm):
    """Form verifikasi, penetapan keputusan, dan persetujuan perubahan desil oleh petugas."""
    status = SelectField(
        "Keputusan Verifikasi",
        choices=[
            ("disetujui", "Setujui Perubahan Desil (Perbarui Data Profil Warga)"),
            ("ditolak", "Tolak Pengajuan (Kondisi Tidak Sesuai / Berkas Tidak Valid)")
        ],
        validators=[DataRequired(message="Pilih status keputusan.")]
    )
    desil_disetujui = SelectField(
        "Tetapkan Desil Final yang Disetujui",
        coerce=int,
        choices=[(i, f"Desil {i} — {DESIL_INFO[i]['kategori']}") for i in range(1, 11)],
        validators=[DataRequired(message="Pilih desil yang disahkan.")]
    )
    catatan_petugas = TextAreaField(
        "Catatan Verifikasi & Berita Acara Petugas",
        validators=[DataRequired(message="Catatan petugas wajib diisi sebagai dasar audit keputusan.")]
    )
    submit = SubmitField("Sahkan Keputusan Pengajuan")
