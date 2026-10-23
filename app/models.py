import re
import datetime
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index, Enum, JSON
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.extensions import db, login_manager


# =============================================================================
# MASTER INFORMASI KLASIFIKASI DESIL (DTKS / REGSOSEK / BPS)
# =============================================================================
DESIL_INFO = {
    1: {
        "desil": 1,
        "kategori": "Sangat Miskin (Kemiskinan Ekstrem)",
        "label": "Desil 1",
        "deskripsi": "Keluarga dalam 10% kelompok ekonomi terendah. Kondisi rumah tidak layak huni atau sangat sederhana, prioritas utama seluruh program bantuan sosial pemerintah.",
        "kelayakan": "Prioritas Utama Penerima Bansos (Sangat Berhak)",
        "is_layak_bansos": True,
        "badge_class": "danger",
        "bg_color": "#dc3545",
        "kondisi_rumah": "Dinding bilik bambu/kayu lapuk, lantai tanah, atap rumbia/seng tua, sanitasi sangat terbatas."
    },
    2: {
        "desil": 2,
        "kategori": "Miskin",
        "label": "Desil 2",
        "deskripsi": "Keluarga dalam kelompok 11-20% terendah. Rumah semi permanen sederhana, berpenghasilan jauh di bawah kebutuhan hidup layak minimum.",
        "kelayakan": "Berhak Menerima Bansos Reguler",
        "is_layak_bansos": True,
        "badge_class": "warning text-dark",
        "bg_color": "#fd7e14",
        "kondisi_rumah": "Lantai semen kasar/papan sederhana, dinding belum diplester atau semi permanen."
    },
    3: {
        "desil": 3,
        "kategori": "Hampir Miskin",
        "label": "Desil 3",
        "deskripsi": "Keluarga dalam kelompok 21-30%. Kondisi ekonomi rentan terhadap guncangan kenaikan harga atau kehilangan pekerjaan.",
        "kelayakan": "Berhak Menerima Bansos",
        "is_layak_bansos": True,
        "badge_class": "info text-dark",
        "bg_color": "#0dcaf0",
        "kondisi_rumah": "Rumah sederhana layak terbatas, sebagian bata/kayu sederhana."
    },
    4: {
        "desil": 4,
        "kategori": "Rentan Miskin",
        "label": "Desil 4",
        "deskripsi": "Keluarga dalam kelompok 31-40%. Berada sedikit di atas garis kemiskinan namun rentan jatuh miskin saat situasi krisis ekonomi.",
        "kelayakan": "Berhak Menerima Bansos Bersyarat",
        "is_layak_bansos": True,
        "badge_class": "primary",
        "bg_color": "#0d6efd",
        "kondisi_rumah": "Rumah permanen sederhana dengan fasilitas dasar mencukupi."
    },
    5: {
        "desil": 5,
        "kategori": "Menengah Bawah",
        "label": "Desil 5",
        "deskripsi": "Keluarga dalam kelompok 41-50%. Memiliki kemampuan finansial cukup untuk pemenuhan kebutuhan primer harian.",
        "kelayakan": "Tidak Berhak Bansos (Kategori Menengah)",
        "is_layak_bansos": False,
        "badge_class": "secondary",
        "bg_color": "#6c757d",
        "kondisi_rumah": "Rumah permanen standar layak huni."
    },
    6: {
        "desil": 6,
        "kategori": "Menengah",
        "label": "Desil 6",
        "deskripsi": "Keluarga dalam kelompok 51-60%. Kondisi ekonomi tergolong stabil dan berkecukupan.",
        "kelayakan": "Tidak Berhak Bansos (Keluarga Mandiri)",
        "is_layak_bansos": False,
        "badge_class": "secondary",
        "bg_color": "#6c757d",
        "kondisi_rumah": "Rumah permanen berlantai keramik dan terawat."
    },
    7: {
        "desil": 7,
        "kategori": "Menengah Cukup",
        "label": "Desil 7",
        "deskripsi": "Keluarga dalam kelompok 61-70%. Memiliki kapasitas ekonomi di atas rata-rata dengan aset dan fasilitas memadai.",
        "kelayakan": "Tidak Berhak Bansos (Tergolong Mampu)",
        "is_layak_bansos": False,
        "badge_class": "dark",
        "bg_color": "#495057",
        "kondisi_rumah": "Rumah permanen bagus, luas, memiliki garasi atau kendaraan bermotor."
    },
    8: {
        "desil": 8,
        "kategori": "Menengah Atas",
        "label": "Desil 8",
        "deskripsi": "Keluarga dalam kelompok 71-80%. Finansial mapan dengan kepemilikan aset bernilai tinggi.",
        "kelayakan": "Tidak Berhak Bansos (Mampu)",
        "is_layak_bansos": False,
        "badge_class": "dark",
        "bg_color": "#343a40",
        "kondisi_rumah": "Rumah permanen mewah bertingkat di kawasan perumahan mapan."
    },
    9: {
        "desil": 9,
        "kategori": "Mampu",
        "label": "Desil 9",
        "deskripsi": "Keluarga dalam kelompok 81-90%. Sangat mapan secara finansial dan berpendapatan tinggi.",
        "kelayakan": "Tidak Berhak Bansos (Sangat Mampu)",
        "is_layak_bansos": False,
        "badge_class": "dark",
        "bg_color": "#212529",
        "kondisi_rumah": "Rumah mewah berfasilitas lengkap dan kendaraan lebih dari satu."
    },
    10: {
        "desil": 10,
        "kategori": "Sangat Mampu / Kaya",
        "label": "Desil 10",
        "deskripsi": "Keluarga dalam 10% kelompok teratas. Golongan ekonomi paling kaya dan sejahtera secara nasional.",
        "kelayakan": "Tidak Berhak Bansos (Golongan Teratas)",
        "is_layak_bansos": False,
        "badge_class": "dark",
        "bg_color": "#212529",
        "kondisi_rumah": "Rumah mewah elit, fasilitas modern lengkap."
    }
}


def get_desil_info(desil: int):
    """Mengembalikan rincian metadata keterangan desil berdasarkan integer desil 1-10."""
    try:
        val = int(desil) if desil is not None else 1
    except Exception:
        val = 1
    return DESIL_INFO.get(val, {
        "desil": val,
        "kategori": f"Desil {val}",
        "label": f"Desil {val}",
        "deskripsi": "Status klasifikasi desil kependudukan.",
        "kelayakan": "Perlu Verifikasi Lapangan",
        "is_layak_bansos": (val <= 4),
        "badge_class": "info",
        "bg_color": "#0dcaf0",
        "kondisi_rumah": "-"
    })


# =============================================================================
# 1. MODEL: User (Petugas, Administrator, & Warga)
# =============================================================================
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nama = Column(String(100), nullable=False)
    role = Column(
        Enum("admin", "petugas_verifikasi", "warga", name="user_role_enum"),
        nullable=False,
        default="warga"
    )
    nik = Column(String(16), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationship
    verifikasi = relationship("Verifikasi", back_populates="petugas")

    def set_password(self, password: str):
        """Menghash password menggunakan werkzeug."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Memverifikasi kecocokan password."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_petugas(self) -> bool:
        return self.role == "petugas_verifikasi"

    @property
    def is_warga(self) -> bool:
        return self.role == "warga"

    @property
    def data_warga(self):
        """Mengambil data Warga yang terkait dengan akun ini melalui NIK."""
        if not self.nik:
            return None
        return Warga.query.filter_by(nik=self.nik).first()

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# =============================================================================
# 2. MODEL: Keluarga (Kartu Keluarga)
# =============================================================================
class Keluarga(db.Model):
    __tablename__ = "keluarga"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nomor_kk = Column(String(16), unique=True, nullable=False, index=True)
    kepala_keluarga = Column(String(100), nullable=False)
    alamat = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships: ON DELETE RESTRICT
    warga_list = relationship("Warga", back_populates="keluarga")

    @validates("nomor_kk")
    def validate_nomor_kk(self, key, nomor_kk):
        if not nomor_kk or not isinstance(nomor_kk, str):
            raise ValueError("Nomor KK wajib diisi.")
        nomor_kk = nomor_kk.strip()
        if not re.match(r"^\d{16}$", nomor_kk):
            raise ValueError("Nomor KK harus tepat 16 digit angka numerik.")
        return nomor_kk

    def __repr__(self):
        return f"<Keluarga {self.nomor_kk} - {self.kepala_keluarga}>"


# =============================================================================
# 3. MODEL: Warga (Calon Penerima Bantuan)
# =============================================================================
class Warga(db.Model):
    __tablename__ = "warga"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_keluarga = Column(
        Integer, 
        ForeignKey("keluarga.id", ondelete="RESTRICT", onupdate="CASCADE"), 
        nullable=False, 
        index=True
    )
    nik = Column(String(16), unique=True, nullable=False, index=True)
    nama = Column(String(100), nullable=False)
    alamat = Column(Text, nullable=False)
    penghasilan = Column(Numeric(15, 2), nullable=False)
    jumlah_tanggungan = Column(Integer, nullable=False, default=0)
    nilai_aset = Column(Numeric(15, 2), nullable=False, default=0.0)
    tanggal_lahir = Column(Date, nullable=False)
    
    # Atribut Desil & Dokumentasi Rumah
    desil = Column(Integer, nullable=True, default=None, comment="Tingkat desil kesejahteraan 1-10")
    foto_rumah = Column(String(255), nullable=True, default=None, comment="Path file atau URL foto tampak depan rumah")
    
    # Parameter Aset Fisik & Infrastruktur Terperinci (Revisi Dosen)
    status_rumah = Column(String(50), nullable=True, default="milik_sendiri", comment="Status kepemilikan rumah: milik_sendiri, sewa_kontrak, menumpang")
    luas_tanah = Column(Numeric(10, 2), nullable=True, default=Decimal("36.00"), comment="Luas bangunan atau tanah rumah dalam m2")
    daya_listrik = Column(Integer, nullable=True, default=450, comment="Daya meteran listrik PLN dalam VA (450, 900, 1300, 2200, 0)")
    jenis_kendaraan = Column(String(50), nullable=True, default="tidak_ada", comment="Kepemilikan kendaraan: tidak_ada, motor, mobil, motor_dan_mobil")
    jumlah_kendaraan = Column(Integer, nullable=True, default=0, comment="Jumlah unit kendaraan bermotor yang dimiliki")
    foto_kendaraan = Column(String(255), nullable=True, default=None, comment="Path file foto bukti kepemilikan kendaraan")
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    keluarga = relationship("Keluarga", back_populates="warga_list")
    verifikasi_list = relationship("Verifikasi", back_populates="warga")
    pengajuan_desil_list = relationship(
        "PengajuanDesil", 
        back_populates="warga", 
        cascade="all, delete-orphan", 
        order_by="PengajuanDesil.tanggal_pengajuan.desc()"
    )

    # Index tambahan
    __table_args__ = (
        Index("idx_warga_nik", "nik"),
        Index("idx_warga_id_keluarga", "id_keluarga"),
        Index("idx_warga_desil", "desil"),
    )

    # Validasi Dasar Model
    @validates("nik")
    def validate_nik(self, key, nik):
        if not nik or not isinstance(nik, str):
            raise ValueError("NIK wajib diisi.")
        nik = nik.strip()
        if not re.match(r"^\d{16}$", nik):
            raise ValueError("NIK harus tepat 16 digit angka numerik.")
        return nik

    @validates("nama")
    def validate_nama(self, key, nama):
        if not nama or not nama.strip():
            raise ValueError("Nama lengkap warga tidak boleh kosong.")
        return nama.strip()

    @validates("alamat")
    def validate_alamat(self, key, alamat):
        if not alamat or not alamat.strip():
            raise ValueError("Alamat tinggal warga tidak boleh kosong.")
        return alamat.strip()

    @validates("penghasilan")
    def validate_penghasilan(self, key, penghasilan):
        if penghasilan is None:
            raise ValueError("Penghasilan wajib diisi.")
        try:
            val = Decimal(str(penghasilan))
        except Exception:
            raise ValueError("Penghasilan harus bernilai numerik valid.")
        if val < Decimal("0"):
            raise ValueError("Penghasilan tidak boleh bernilai negatif (>= 0).")
        return val

    @validates("jumlah_tanggungan")
    def validate_jumlah_tanggungan(self, key, tanggungan):
        if tanggungan is None:
            return 0
        try:
            val = int(tanggungan)
        except Exception:
            raise ValueError("Jumlah tanggungan harus berupa bilangan bulat integer.")
        if val < 0:
            raise ValueError("Jumlah tanggungan tidak boleh negatif (>= 0).")
        return val

    @validates("nilai_aset")
    def validate_nilai_aset(self, key, aset):
        if aset is None:
            return Decimal("0.00")
        try:
            val = Decimal(str(aset))
        except Exception:
            raise ValueError("Nilai aset harus bernilai numerik valid.")
        if val < Decimal("0"):
            raise ValueError("Nilai aset tidak boleh bernilai negatif (>= 0).")
        return val

    @validates("tanggal_lahir")
    def validate_tanggal_lahir(self, key, tanggal_lahir):
        if not tanggal_lahir:
            raise ValueError("Tanggal lahir wajib diisi.")
        if isinstance(tanggal_lahir, str):
            try:
                tanggal_lahir = datetime.datetime.strptime(tanggal_lahir.strip(), "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Format tanggal lahir tidak valid (harus YYYY-MM-DD).")
        if tanggal_lahir > datetime.date.today():
            raise ValueError("Tanggal lahir tidak boleh berada di masa depan.")
        return tanggal_lahir

    @validates("desil")
    def validate_desil(self, key, val):
        if val is None or str(val).strip() in ("", "0", "None"):
            return None
        try:
            d = int(val)
        except Exception:
            raise ValueError("Nilai desil harus berupa angka bulat 1 sampai 10.")
        if d < 1 or d > 10:
            raise ValueError("Nilai desil harus berada pada rentang 1 sampai 10.")
        return d

    @validates("luas_tanah")
    def validate_luas_tanah(self, key, val):
        if val is None or str(val).strip() == "":
            return Decimal("36.00")
        try:
            d = Decimal(str(val))
        except Exception:
            raise ValueError("Luas bangunan harus berupa nilai numerik valid.")
        if d <= Decimal("0"):
            raise ValueError("Luas bangunan harus bernilai positif lebih dari 0 m².")
        return d

    # Helper & Properties untuk Desil & Foto Rumah
    @property
    def keterangan_desil(self):
        """Mengambil data kamus keterangan desil warga saat ini."""
        val = self.desil if self.desil is not None else self.hitung_desil_otomatis()
        return get_desil_info(val)

    @property
    def foto_rumah_url(self):
        """Mengembalikan path url foto rumah warga atau ilustrasi default fallback."""
        if self.foto_rumah and str(self.foto_rumah).strip():
            return self.foto_rumah
        # Fallback ilustrasi berbasis desil
        val = self.desil if self.desil is not None else self.hitung_desil_otomatis()
        if val == 1:
            return "images/rumah/rumah_desil1_bilik.svg"
        elif val == 2:
            return "images/rumah/rumah_desil2_sederhana.svg"
        elif val in [3, 4]:
            return "images/rumah/rumah_desil3_semipermanen.svg"
        elif val in [5, 6, 7]:
            return "images/rumah/rumah_desil7_permanen.svg"
        else:
            return "images/rumah/rumah_desil10_mewah.svg"

    @property
    def status_rumah_label(self):
        mapping = {
            "milik_sendiri": "Milik Sendiri",
            "sewa_kontrak": "Sewa / Kontrak",
            "menumpang": "Menumpang / Milik Kerabat"
        }
        return mapping.get(self.status_rumah, "Milik Sendiri")

    @property
    def daya_listrik_label(self):
        mapping = {
            450: "450 VA (Bersubsidi)",
            900: "900 VA (Bersubsidi / Prasejahtera)",
            1300: "1.300 VA (Non-Subsidi)",
            2200: "2.200 VA+ (Mampu)",
            0: "Non-PLN / Menumpang Tetangga"
        }
        return mapping.get(self.daya_listrik, f"{self.daya_listrik} VA" if self.daya_listrik else "450 VA")

    @property
    def jenis_kendaraan_label(self):
        mapping = {
            "tidak_ada": "Tidak Ada Kendaraan",
            "motor": "Sepeda Motor",
            "mobil": "Mobil Pribadi",
            "motor_dan_mobil": "Motor & Mobil"
        }
        return mapping.get(self.jenis_kendaraan, "Tidak Ada")

    @property
    def foto_kendaraan_url(self):
        if self.foto_kendaraan and str(self.foto_kendaraan).strip():
            return self.foto_kendaraan
        return None

    def hitung_estimasi_aset_otomatis(self) -> Decimal:
        """
        Menghitung estimasi total nilai aset secara objektif:
        1. Nilai Bangunan/Tanah (jika milik sendiri: luas x Rp 1.500.000 / m2)
        2. Nilai Kendaraan (motor Rp 6.000.000 / unit, mobil Rp 75.000.000 / unit)
        """
        total = Decimal("0.00")
        status = self.status_rumah or "milik_sendiri"
        luas = float(self.luas_tanah or 0)
        if status == "milik_sendiri":
            efektif_luas = max(luas, 20.0) if luas > 0 else 20.0
            total += Decimal(str(round(efektif_luas * 1500000, 2)))
        else:
            total += Decimal("0.00")

        jenis = self.jenis_kendaraan or "tidak_ada"
        jumlah = max(0, int(self.jumlah_kendaraan or 0))
        if jenis == "motor":
            total += Decimal(str(max(jumlah, 1) * 6000000))
        elif jenis == "mobil":
            total += Decimal(str(max(jumlah, 1) * 75000000))
        elif jenis == "motor_dan_mobil":
            total += Decimal(str(max(jumlah, 1) * 85000000))

        return total


    @staticmethod
    def kalkulasi_desil_lengkap(
        penghasilan,
        jumlah_tanggungan=0,
        status_rumah="milik_sendiri",
        luas_tanah=36,
        daya_listrik=450,
        jenis_kendaraan="tidak_ada",
        jumlah_kendaraan=0,
        nilai_aset=0
    ) -> dict:
        """
        Kalkulasi indikator komposit kesejahteraan & desil (1-10) berdasarkan
        metode Proxy-Means Testing (PMT) indikator BPS & DTKS Kemensos.
        Mengembalikan dictionary lengkap berisi:
        - desil: int (1-10)
        - label, kategori, deskripsi, kelayakan, is_layak_bansos
        - badge_class, bg_color, per_kapita, faktor_penentu
        """
        try:
            p = Decimal(str(penghasilan or 0))
            if p < Decimal("0"):
                p = Decimal("0")
            t = max(0, int(jumlah_tanggungan or 0))
        except Exception:
            p = Decimal("0")
            t = 0

        per_kapita = p / max(1, t + 1)

        # 1. Base Decile dari Pendapatan & Beban Tanggungan (BPS/DTKS)
        if per_kapita < Decimal("600000") or (p <= Decimal("1000000") and t >= 2):
            d_inc = 1
        elif per_kapita < Decimal("950000") or p <= Decimal("1800000"):
            d_inc = 2
        elif per_kapita < Decimal("1400000") or p <= Decimal("2600000"):
            d_inc = 3
        elif per_kapita < Decimal("1900000") or p <= Decimal("3800000"):
            d_inc = 4
        elif per_kapita < Decimal("2700000") or p <= Decimal("5000000"):
            d_inc = 5
        elif per_kapita < Decimal("3800000") or p <= Decimal("7500000"):
            d_inc = 6
        elif per_kapita < Decimal("5500000") or p <= Decimal("10000000"):
            d_inc = 7
        elif per_kapita < Decimal("8000000") or p <= Decimal("15000000"):
            d_inc = 8
        elif per_kapita < Decimal("13000000") or p <= Decimal("25000000"):
            d_inc = 9
        else:
            d_inc = 10

        daya = int(daya_listrik or 450)
        jenis = str(jenis_kendaraan or "tidak_ada").lower()
        jml_k = max(0, int(jumlah_kendaraan or 0))
        status = str(status_rumah or "milik_sendiri").lower()
        luas = max(0, float(luas_tanah or 36))
        aset = max(0.0, float(nilai_aset or 0))

        d_final = d_inc
        faktor_penentu = []

        # Aturan Indikator Aset Fisik & Infrastruktur
        if jenis in ("mobil", "motor_dan_mobil") or daya >= 2200 or aset >= 100000000:
            d_final = max(d_final, 7)
            if jenis in ("mobil", "motor_dan_mobil"):
                faktor_penentu.append("Kepemilikan mobil pribadi (golongan mampu)")
            if daya >= 2200:
                faktor_penentu.append(f"Daya listrik {daya} VA non-subsidi mandiri")
            if aset >= 100000000:
                faktor_penentu.append(f"Total estimasi aset tinggi (Rp {int(aset):,})")
        elif daya == 1300 or (jenis == "motor" and jml_k >= 2) or luas >= 100 or aset >= 50000000:
            d_final = max(d_final, 5)
            if daya == 1300:
                faktor_penentu.append("Daya listrik 1.300 VA non-subsidi (golongan menengah)")
            if jenis == "motor" and jml_k >= 2:
                faktor_penentu.append(f"Kepemilikan {jml_k} unit sepeda motor")
        elif (status == "menumpang" or daya == 0) and p <= Decimal("2000000") and jenis == "tidak_ada":
            d_final = min(d_final, 2)
            if daya == 0:
                faktor_penentu.append("Kondisi rumah non-PLN (kemiskinan ekstrem)")
            if status == "menumpang":
                faktor_penentu.append("Status tempat tinggal menumpang tanpa kepemilikan aset")
        else:
            faktor_penentu.append(f"Pendapatan per kapita Rp {int(per_kapita):,}/bulan")

        desil = max(1, min(10, d_final))
        info = get_desil_info(desil)

        return {
            "desil": desil,
            "label": f"Desil {desil}",
            "kategori": info.get("kategori", f"Desil {desil}"),
            "deskripsi": info.get("deskripsi", ""),
            "kelayakan": info.get("kelayakan", ""),
            "is_layak_bansos": info.get("is_layak_bansos", False),
            "badge_class": info.get("badge_class", "primary"),
            "bg_color": info.get("bg_color", "#0d6efd"),
            "kondisi_rumah": info.get("kondisi_rumah", "-"),
            "per_kapita": float(per_kapita),
            "faktor_penentu": faktor_penentu
        }

    def hitung_desil_otomatis(self) -> int:
        """
        Menghitung estimasi desil secara otomatis berbasis indikator aset,
        kelistrikan, dan pendapatan per kapita (Proxy-Means Testing).
        """
        res = self.kalkulasi_desil_lengkap(
            penghasilan=self.penghasilan,
            jumlah_tanggungan=self.jumlah_tanggungan,
            status_rumah=self.status_rumah,
            luas_tanah=self.luas_tanah,
            daya_listrik=self.daya_listrik,
            jenis_kendaraan=self.jenis_kendaraan,
            jumlah_kendaraan=self.jumlah_kendaraan,
            nilai_aset=self.nilai_aset
        )
        return res["desil"]

    def __repr__(self):
        return f"<Warga {self.nik} - {self.nama} (Desil: {self.desil})>"


# =============================================================================
# 4. MODEL: ProgramBantuan (Daftar Program Bantuan Sosial)
# =============================================================================
class ProgramBantuan(db.Model):
    __tablename__ = "program_bantuan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nama_program = Column(String(100), nullable=False)
    kriteria_penghasilan_max = Column(Numeric(15, 2), nullable=False)
    kriteria_tanggungan_min = Column(Integer, nullable=False, default=0)
    kriteria_aset_max = Column(Numeric(15, 2), nullable=True)
    kriteria_desil_max = Column(Integer, nullable=True, default=4, comment="Batas maksimal desil yang berhak (default desil 4 / rentan miskin)")
    deskripsi = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    verifikasi_list = relationship("Verifikasi", back_populates="program")

    @validates("nama_program")
    def validate_nama_program(self, key, nama):
        if not nama or not nama.strip():
            raise ValueError("Nama program bantuan tidak boleh kosong.")
        return nama.strip()

    @validates("kriteria_penghasilan_max")
    def validate_penghasilan_max(self, key, val):
        if val is None:
            raise ValueError("Kriteria batas maksimum penghasilan wajib diisi.")
        try:
            d = Decimal(str(val))
        except Exception:
            raise ValueError("Kriteria penghasilan maksimum harus berupa nilai numerik.")
        if d < Decimal("0"):
            raise ValueError("Kriteria penghasilan maksimum tidak boleh negatif.")
        return d

    @validates("kriteria_tanggungan_min")
    def validate_tanggungan_min(self, key, val):
        if val is None:
            return 0
        try:
            i = int(val)
        except Exception:
            raise ValueError("Kriteria tanggungan minimum harus berupa bilangan bulat.")
        if i < 0:
            raise ValueError("Kriteria tanggungan minimum tidak boleh negatif.")
        return i

    @validates("kriteria_aset_max")
    def validate_aset_max(self, key, val):
        if val is None or str(val).strip() == "":
            return None
        try:
            d = Decimal(str(val))
        except Exception:
            raise ValueError("Kriteria aset maksimum harus berupa nilai numerik.")
        if d < Decimal("0"):
            raise ValueError("Kriteria aset maksimum tidak boleh negatif.")
        return d

    @validates("kriteria_desil_max")
    def validate_desil_max(self, key, val):
        if val is None or str(val).strip() in ("", "0", "None"):
            return None
        try:
            d = int(val)
        except Exception:
            raise ValueError("Kriteria desil maksimal harus berupa bilangan bulat 1-10.")
        if d < 1 or d > 10:
            raise ValueError("Kriteria desil maksimal harus bernilai antara 1 sampai 10.")
        return d

    def __repr__(self):
        return f"<ProgramBantuan {self.id} - {self.nama_program} (Maks Desil: {self.kriteria_desil_max})>"


# =============================================================================
# 5. MODEL: Verifikasi (Hasil Evaluasi & Verifikasi Kelayakan)
# =============================================================================
class Verifikasi(db.Model):
    __tablename__ = "verifikasi"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_warga = Column(
        Integer, 
        ForeignKey("warga.id", ondelete="RESTRICT", onupdate="CASCADE"), 
        nullable=False, 
        index=True
    )
    id_program = Column(
        Integer, 
        ForeignKey("program_bantuan.id", ondelete="RESTRICT", onupdate="CASCADE"), 
        nullable=False, 
        index=True
    )
    id_petugas = Column(
        Integer, 
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"), 
        nullable=False
    )
    
    # Status otomatis dari rule engine
    status_otomatis = Column(
        Enum("layak", "tidak_layak", "perlu_ditinjau", name="status_otomatis_enum"),
        nullable=False,
        comment="hasil otomatis dari rule engine"
    )

    # Status final setelah konfirmasi petugas
    status_final = Column(
        Enum("layak", "tidak_layak", "perlu_ditinjau", name="status_final_enum"),
        nullable=True,
        comment="hasil setelah konfirmasi petugas, NULL jika belum dikonfirmasi"
    )

    catatan_petugas = Column(Text, nullable=True)
    detail_pengecekan = Column(JSON, nullable=True, comment="simpan breakdown kriteria mana yang lolos/gagal, untuk audit")
    tanggal_verifikasi = Column(DateTime, server_default=func.now())
    tanggal_konfirmasi = Column(DateTime, nullable=True)

    # Property alias status_sistem
    @property
    def status_sistem(self):
        return self.status_otomatis

    @status_sistem.setter
    def status_sistem(self, val):
        self.status_otomatis = val

    # Relationships: back_populates
    warga = relationship("Warga", back_populates="verifikasi_list")
    program = relationship("ProgramBantuan", back_populates="verifikasi_list")
    petugas = relationship("User", back_populates="verifikasi")

    # Constraints & Indexes
    __table_args__ = (
        UniqueConstraint("id_warga", "id_program", name="uq_warga_program"),
        Index("idx_verifikasi_id_warga", "id_warga"),
        Index("idx_verifikasi_id_program", "id_program"),
        Index("idx_verifikasi_tanggal", "tanggal_verifikasi"),
    )

    def __repr__(self):
        return f"<Verifikasi Warga:{self.id_warga} Prog:{self.id_program} Status:{self.status_otomatis}>"


# =============================================================================
# 6. MODEL: PengajuanDesil (Permohonan & Sanggah Perubahan Desil Warga)
# =============================================================================
class PengajuanDesil(db.Model):
    __tablename__ = "pengajuan_desil"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_warga = Column(
        Integer, 
        ForeignKey("warga.id", ondelete="CASCADE", onupdate="CASCADE"), 
        nullable=False, 
        index=True
    )
    id_user = Column(
        Integer, 
        ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"), 
        nullable=False, 
        index=True
    )
    desil_lama = Column(Integer, nullable=False, comment="Desil awal sebelum pengajuan perubahan")
    desil_diajukan = Column(Integer, nullable=False, comment="Desil baru yang diajukan oleh pemohon")
    penghasilan_terkini = Column(Numeric(15, 2), nullable=False, comment="Bukti penghasilan bulanan riil saat ini")
    jumlah_tanggungan = Column(Integer, nullable=True, default=0, comment="Jumlah tanggungan riil saat ini")
    foto_rumah_baru = Column(String(255), nullable=False, comment="Path file foto tampak depan rumah yang diunggah")
    dokumen_pendukung = Column(String(255), nullable=True, comment="Path berkas pendukung (SKTM/slip gaji/foto dalam)")
    alasan_pengajuan = Column(Text, nullable=False, comment="Alasan warga mengapa desil awal keliru")
    status = Column(
        Enum("menunggu", "disetujui", "ditolak", name="status_pengajuan_desil_enum"),
        nullable=False,
        default="menunggu",
        index=True
    )
    catatan_petugas = Column(Text, nullable=True, comment="Catatan / pertimbangan evaluasi petugas")
    id_petugas = Column(
        Integer, 
        ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE"), 
        nullable=True
    )
    tanggal_pengajuan = Column(DateTime, server_default=func.now())
    tanggal_verifikasi = Column(DateTime, nullable=True)

    # Relationships
    warga = relationship("Warga", back_populates="pengajuan_desil_list")
    pemohon = relationship("User", foreign_keys=[id_user])
    petugas = relationship("User", foreign_keys=[id_petugas])

    __table_args__ = (
        Index("idx_pengajuan_desil_warga", "id_warga"),
        Index("idx_pengajuan_desil_status", "status"),
        Index("idx_pengajuan_desil_tanggal", "tanggal_pengajuan"),
    )

    @property
    def keterangan_desil_lama(self):
        return get_desil_info(self.desil_lama)

    @property
    def keterangan_desil_diajukan(self):
        return get_desil_info(self.desil_diajukan)

    def __repr__(self):
        return f"<PengajuanDesil ID:{self.id} Warga:{self.id_warga} {self.desil_lama}->{self.desil_diajukan} ({self.status})>"
