from app import create_app, db

app = create_app()

def migrate_database():
    with app.app_context():
        conn = db.engine.connect()
        try:
            res = conn.execute(db.text("DESCRIBE warga")).fetchall()
            existing_cols = [r[0] for r in res]
            
            new_columns = [
                ("status_rumah", "VARCHAR(50) DEFAULT 'milik_sendiri'"),
                ("luas_tanah", "INT DEFAULT 36"),
                ("daya_listrik", "INT DEFAULT 450"),
                ("jenis_kendaraan", "VARCHAR(50) DEFAULT 'tidak_ada'"),
                ("jumlah_kendaraan", "INT DEFAULT 0"),
                ("foto_kendaraan", "VARCHAR(255) NULL")
            ]
            
            for col_name, col_def in new_columns:
                if col_name not in existing_cols:
                    print(f"Menambahkan kolom '{col_name}' ke tabel warga di MySQL...")
                    conn.execute(db.text(f"ALTER TABLE warga ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    print(f"Kolom '{col_name}' berhasil ditambahkan.")
                else:
                    print(f"Kolom '{col_name}' sudah ada.")
            
            print("\nMigrasi database selesai! Semua kolom parameter aset sudah tersedia di MySQL.")
        finally:
            conn.close()

if __name__ == "__main__":
    migrate_database()

