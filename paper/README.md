# Panduan Kompilasi Paper LaTeX (Springer LNCS)

Folder ini berisi naskah ilmiah lengkap dalam format **Springer Nature - Lecture Notes in Computer Science (LNCS)** berdasarkan dokumen `Springer_Nature_Lecture_Notes_in_Computer_Science.pdf`.

---

## 📁 Struktur Berkas

| Berkas | Keterangan |
|---|---|
| `main.tex` | Naskah utama LaTeX lengkap dengan seluruh bagian, tabel, dan gambar |
| `references.bib` | Berkas BibTeX berisi 16 referensi lengkap sesuai naskah asli |
| `llncs.cls` | Kelas dokumen resmi Springer LNCS (diambil dari CTAN) |
| `splncs04.bst` | File gaya bibliografi resmi Springer LNCS |
| `status_diagram_fig.png` | Gambar diagram alur verifikasi (Gambar 1 / *Fig. 1*) |
| `Springer_Nature_Lecture_Notes_in_Computer_Science.pdf` | Dokumen PDF referensi asli |

---

## 🚀 Cara Kompilasi

### 1. Menggunakan Overleaf (Paling Mudah)
1. Buka [Overleaf](https://www.overleaf.com/).
2. Buat proyek baru (*New Project* $\rightarrow$ *Upload Project*).
3. Unggah seluruh isi folder `paper` (atau arsip ZIP dari folder ini).
4. Pastikan compiler diatur ke **pdfLaTeX** (default Overleaf).
5. Klik **Recompile**.

### 2. Menggunakan Baris Perintah (TeX Live / MiKTeX)
Jalankan urutan perintah berikut di terminal / PowerShell:
```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Atau menggunakan `latexmk`:
```bash
latexmk -pdf main.tex
```

---

## 📑 Rincian Bagian Naskah

1. **Judul & Penulis**:
   - *Title*: Evaluating Rule Compliance and Decision Traceability in a Social Assistance Eligibility Prototype
   - *Authors*: Dzaky Ahsanal Khuluq, Annisa Nailatul Izzah (PENS)
2. **Abstrak & Kata Kunci**: Evaluasi prototipe Sociovault dengan 3-stage rule engine.
3. **Bagian 1**: Introduction (Latar belakang bantuan sosial, risiko penanganan, kepatuhan aturan & keterlacakan).
4. **Bagian 2**: Related Work (Subbagian 2.1 s.d. 2.5 dan Tabel 1 pembanding studi terkait).
5. **Bagian 3**: Methodology:
   - 3.1 Kriteria Program A (Tabel 2)
   - 3.2 Diagram Alur Verifikasi (Gambar 1)
   - 3.3 Matriks Status Awal, Aksi, Peran & Status Akhir (Tabel 3)
   - 3.4 s.d. 3.7 Evaluasi Aturan, Estimasi Desil, Pencegahan Duplikasi, dll.
6. **Bagian 4**: Experimental Design:
   - 4.1 Uji 1 (Kepatuhan Aturan - 60 kasus sintetis, Tabel 4 & Tabel 5)
   - 4.2 Hasil yang Diharapkan Uji 1
   - 4.3 Uji 2 (Nilai Ambang Batas & Verifikasi Duplikat, Tabel Nilai Batas)
   - 4.4 Hasil yang Diharapkan Uji 2
   - 4.5 & 4.6 Uji 3 (Keterlacakan Petugas)
   - 4.7 Ringkasan Output Eksperimen (Tabel 6, Tabel 7, Tabel 8, Tabel 9)
7. **Bagian 5**: Conclusion (4 aspek kesimpulan utama).
8. **Daftar Pustaka**: 16 referensi (Undang-Undang, regulasi SPBE & PDP, dokumentasi Flask & SQLAlchemy, publikasi AI Wei et al., Sunny, GAO, circular California, OpenG2P, openIMIS, DSWD, dan Owino).
