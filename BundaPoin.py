# ==============================================================================
# BUNDAPOIN - Prototipe Aplikasi Gamifikasi Pendamping Ibu & Anak (0-3 Tahun)
# ==============================================================================

import sqlite3
import hashlib
import calendar
from datetime import date, datetime, timedelta
import streamlit as st
import pandas as pd

# ==============================================================================
# 1. KONSTANTA POIN, HARGA HADIAH, JADWAL, & KONFIGURASI
# ==============================================================================

NAMA_APLIKASI = "BundaPoin"
DB_FILE = "bundapoin.db"

# Aturan Poin Laporan & Streak
POIN_LAPOR_HARIAN = 10
TARGET_STREAK_HARI = 7
POIN_BONUS_STREAK = 30

# Aturan Poin Kunjungan Posyandu (diverifikasi Kader)
POIN_DATANG_POSYANDU = 50
POIN_IMUNISASI_JADWAL = 100
POIN_BERAT_NAIK_KURVA = 75
POIN_KUNJUNGAN_LUAR_JADWAL = 60  # Poin tambahan jika memenuhi panggilan Kader di luar jadwal rutin

# Jadwal Rutin Posyandu (1 kali sebulan setiap tanggal 10)
TANGGAL_RUTIN_POSYANDU = 10
JAM_OPERASIONAL_POSYANDU = "08.00 – 11.00 WIB"

# Batas Usia Anak (dalam bulan: 3 tahun = 36 bulan)
BATAS_USIA_MAKS_BULAN = 36
BATAS_USIA_ASI_EKSKLUSIF_BULAN = 6

# Kode Rahasia Login Kader Posyandu (untuk demo lomba)
KODE_LOGIN_KADER = "POSYANDU2026"

# Katalog Hadiah
KATALOG_HADIAH = [
    {
        "id": "popok_pack",
        "nama": "Popok Bayi/Balita (1 Pack)",
        "harga": 500,
        "ikon": "🧷",
        "deskripsi": "1 pack popok sekali pakai ukuran S/M/L/XL sesuai berat anak.",
        "harus_di_atas_6_bulan": False,
    },
    {
        "id": "susu_mpasi",
        "nama": "Paket Susu Pertumbuhan / MPASI Fortifikasi",
        "harga": 700,
        "ikon": "🥣",
        "deskripsi": "Susu pertumbuhan atau bubur MPASI bergizi tinggi zat besi.",
        "harus_di_atas_6_bulan": True,  # Hanya muncul jika anak berusia > 6 bulan
    },
    {
        "id": "voucher_bayi",
        "nama": "Voucher Kebutuhan Anak Rp25.000",
        "harga": 300,
        "ikon": "🎟️",
        "deskripsi": "Voucher belanja minyak telon, sabun bayi, atau tisu basah di koperasi Posyandu.",
        "harus_di_atas_6_bulan": False,
    },
]


# ==============================================================================
# 2. FUNGSI KEAMANAN, WAKTU SIMULASI (DEV TOOLS), & JADWAL
# ==============================================================================

def tanggal_aktif() -> date:
    """
    Mengembalikan tanggal hari ini (atau tanggal simulasi jika Developer Tools sedang menggeser hari).
    """
    offset_hari = st.session_state.get("dev_offset_hari", 0)
    return date.today() + timedelta(days=offset_hari)


def jam_lokal_aktif() -> int:
    """
    Mengembalikan jam lokal pengguna saat ini (0-23), atau jam simulasi dari Developer Tools.
    Digunakan untuk menentukan Auto Dark Mode (malam: 18:00 - 05:59).
    """
    if st.session_state.get("dev_jam_simulasi") is not None:
        return int(st.session_state["dev_jam_simulasi"])
    return datetime.now().hour


def apakah_mode_gelap_aktif() -> bool:
    """
    Menentukan apakah aplikasi menggunakan tema gelap:
    - Jika pengguna menyalakan toggle manual, ikuti pilihan manual.
    - Jika mode 'Otomatis', aktifkan mode gelap saat jam lokal 18:00 hingga 05:59.
    """
    mode_pilihan = st.session_state.get("mode_tema", "Otomatis (Jam Lokal)")
    if mode_pilihan == "🌙 Gelap":
        return True
    if mode_pilihan == "☀️ Terang":
        return False
    jam = jam_lokal_aktif()
    return (jam >= 18) or (jam < 6)


def hash_password(password_polos: str) -> str:
    """Mengubah password teks biasa menjadi hash SHA-256."""
    return hashlib.sha256(password_polos.encode("utf-8")).hexdigest()


def buat_kode_redeem_acak(user_id: int, nama_hadiah: str) -> str:
    """
    Membuat kode klaim redeem acak 6 karakter (misal: #RDM-8F4A2C) menggunakan SHA-256
    dari gabungan user_id, nama_hadiah, dan waktu presisi mikrodetik agar tidak bisa ditebak.
    """
    umpan_acak = f"{user_id}-{nama_hadiah}-{datetime.now().isoformat()}-{id(nama_hadiah)}"
    kode_hex = hashlib.sha256(umpan_acak.encode("utf-8")).hexdigest()[:6].upper()
    return f"#RDM-{kode_hex}"


def hitung_usia_bulan(tgl_lahir_str: str) -> int:
    """Menghitung usia anak dalam satuan bulan penuh dari tanggal lahir (YYYY-MM-DD)."""
    tgl_lahir = datetime.strptime(tgl_lahir_str, "%Y-%m-%d").date()
    hari_ini = tanggal_aktif()
    selisih_bulan = (hari_ini.year - tgl_lahir.year) * 12 + (hari_ini.month - tgl_lahir.month)
    if hari_ini.day < tgl_lahir.day:
        selisih_bulan -= 1
    return max(0, selisih_bulan)


def usia_lebih_dari_6_bulan(tgl_lahir_str: str) -> bool:
    """Mengecek apakah usia anak di atas 6 bulan (> 6 bulan)."""
    return hitung_usia_bulan(tgl_lahir_str) > BATAS_USIA_ASI_EKSKLUSIF_BULAN


def ambil_jadwal_rutin_berikutnya() -> str:
    """Menghitung tanggal jadwal rutin Posyandu (1x sebulan tiap tanggal 10)."""
    hari_ini = tanggal_aktif()
    jadwal_bulan_ini = date(hari_ini.year, hari_ini.month, TANGGAL_RUTIN_POSYANDU)
    if hari_ini <= jadwal_bulan_ini:
        tgl_jadwal = jadwal_bulan_ini
    else:
        if hari_ini.month == 12:
            tgl_jadwal = date(hari_ini.year + 1, 1, TANGGAL_RUTIN_POSYANDU)
        else:
            tgl_jadwal = date(hari_ini.year, hari_ini.month + 1, TANGGAL_RUTIN_POSYANDU)
    return f"{tgl_jadwal.strftime('%d-%m-%Y')} ({JAM_OPERASIONAL_POSYANDU})"


# ==============================================================================
# 3. FUNGSI DATABASE (SQLite) & DATA CONTOH (SEED)
# ==============================================================================

def get_connection():
    """Membuka koneksi ke database SQLite lokal."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Membuat tabel database jika belum ada dan mengisi data contoh (seed)."""
    conn = get_connection()
    cur = conn.cursor()

    # 1. Tabel Akun Ibu & Anak
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_ibu TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nama_anak TEXT NOT NULL,
            tgl_lahir_anak TEXT NOT NULL,
            no_akta TEXT UNIQUE NOT NULL,
            poin INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            tgl_lapor_terakhir TEXT
        )
    """)

    # 2. Tabel Laporan Harian
    cur.execute("""
        CREATE TABLE IF NOT EXISTS laporan_harian (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tanggal TEXT NOT NULL,
            status_sehat TEXT NOT NULL,
            status_makan TEXT NOT NULL,
            status_tidur TEXT NOT NULL,
            catatan TEXT,
            poin_didapat INTEGER NOT NULL,
            UNIQUE(user_id, tanggal),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 3. Tabel Kunjungan Posyandu (Rutin Bulanan & Luar Jadwal)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kunjungan_posyandu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tanggal TEXT NOT NULL,
            bulan_tahun TEXT NOT NULL,
            jenis_kunjungan TEXT DEFAULT 'Rutin Bulanan',
            berat_kg REAL NOT NULL,
            tinggi_cm REAL NOT NULL,
            datang_posyandu INTEGER NOT NULL,
            imunisasi_jadwal INTEGER NOT NULL,
            berat_naik_kurva INTEGER NOT NULL,
            poin_didapat INTEGER NOT NULL,
            catatan_kader TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 4. Tabel Riwayat Penukaran Hadiah (dengan kode_klaim acak & status_ambil)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS riwayat_penukaran (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kode_klaim TEXT,
            tanggal TEXT NOT NULL,
            nama_hadiah TEXT NOT NULL,
            poin_dipakai INTEGER NOT NULL,
            status_ambil TEXT DEFAULT 'Belum Diambil',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 5. Tabel Panggilan Khusus Kader Posyandu (Luar Jadwal)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS panggilan_posyandu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tgl_panggilan TEXT NOT NULL,
            alasan TEXT NOT NULL,
            poin_bonus INTEGER DEFAULT 60,
            status TEXT DEFAULT 'Menunggu Kedatangan',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Migrasi aman untuk database versi sebelumnya
    cur.execute("PRAGMA table_info(riwayat_penukaran)")
    kolom_riwayat = [r["name"] for r in cur.fetchall()]
    if "status_ambil" not in kolom_riwayat:
        cur.execute("ALTER TABLE riwayat_penukaran ADD COLUMN status_ambil TEXT DEFAULT 'Belum Diambil'")
    if "kode_klaim" not in kolom_riwayat:
        cur.execute("ALTER TABLE riwayat_penukaran ADD COLUMN kode_klaim TEXT")

    # Isi kode_klaim acak jika ada data lama yang belum punya kode_klaim
    cur.execute("SELECT id, user_id, nama_hadiah FROM riwayat_penukaran WHERE kode_klaim IS NULL OR kode_klaim = ''")
    for r in cur.fetchall():
        kode_baru = buat_kode_redeem_acak(r["user_id"], f"{r['nama_hadiah']}-{r['id']}")
        cur.execute("UPDATE riwayat_penukaran SET kode_klaim = ? WHERE id = ?", (kode_baru, r["id"]))

    cur.execute("PRAGMA table_info(kunjungan_posyandu)")
    if "jenis_kunjungan" not in [r["name"] for r in cur.fetchall()]:
        cur.execute("ALTER TABLE kunjungan_posyandu ADD COLUMN jenis_kunjungan TEXT DEFAULT 'Rutin Bulanan'")

    # Isi data contoh jika tabel users masih kosong
    cur.execute("SELECT COUNT(*) AS jumlah FROM users")
    if cur.fetchone()["jumlah"] == 0:
        isi_data_contoh(cur)
    else:
        cur.execute("UPDATE OR IGNORE users SET nama_ibu = 'Bunda Maya' WHERE nama_ibu = 'Bunda Siti'")
        cur.execute("UPDATE OR IGNORE users SET nama_ibu = 'Bunda Nur' WHERE nama_ibu = 'Bunda Rina'")

    conn.commit()
    conn.close()


def isi_data_contoh(cur):
    """Menambahkan 2 akun contoh untuk demo lomba (usia anak dalam rentang 0-36 bulan)."""
    hari_ini = tanggal_aktif()
    kemarin = (hari_ini - timedelta(days=1)).isoformat()
    dua_hari_lalu = (hari_ini - timedelta(days=2)).isoformat()
    besok = (hari_ini + timedelta(days=2)).isoformat()
    bulan_ini = hari_ini.strftime("%Y-%m")

    # Contoh 1: Bunda Maya (Anak ~10 bulan, streak 6 hari)
    tgl_lahir_budi = (hari_ini - timedelta(days=310)).isoformat()
    cur.execute("""
        INSERT INTO users (nama_ibu, password_hash, nama_anak, tgl_lahir_anak, no_akta, poin, streak, tgl_lapor_terakhir)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Bunda Maya", hash_password("123456"), "Budi Santoso", tgl_lahir_budi, "3275-LU-102938-2025", 680, 6, kemarin))
    id_maya = cur.lastrowid

    cur.execute("""
        INSERT INTO laporan_harian (user_id, tanggal, status_sehat, status_makan, status_tidur, catatan, poin_didapat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        id_maya, dua_hari_lalu,
        "Sehat & Aktif",
        "Cukup (Makan 3x sehari + camilan/ASI)",
        "Cukup (10–14 jam sehari, tidur nyenyak)",
        "Lahap makan bubur tim ayam.", 10
    ))
    cur.execute("""
        INSERT INTO laporan_harian (user_id, tanggal, status_sehat, status_makan, status_tidur, catatan, poin_didapat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        id_maya, kemarin,
        "Sehat & Aktif",
        "Cukup (Makan 3x sehari + camilan/ASI)",
        "Cukup (10–14 jam sehari, tidur nyenyak)",
        "Tidur siang nyenyak 2 jam.", 10
    ))

    cur.execute("""
        INSERT INTO kunjungan_posyandu
        (user_id, tanggal, bulan_tahun, jenis_kunjungan, berat_kg, tinggi_cm, datang_posyandu, imunisasi_jadwal, berat_naik_kurva, poin_didapat, catatan_kader)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (id_maya, kemarin, bulan_ini, "Rutin Bulanan", 8.9, 72.5, 1, 1, 1, 225, "Pertumbuhan sangat baik, imunisasi lengkap."))

    kode_contoh = buat_kode_redeem_acak(id_maya, "Voucher Kebutuhan Anak Rp25.000")
    cur.execute("""
        INSERT INTO riwayat_penukaran (user_id, kode_klaim, tanggal, nama_hadiah, poin_dipakai, status_ambil)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (id_maya, kode_contoh, f"{kemarin} 09:30", "Voucher Kebutuhan Anak Rp25.000", 300, "Belum Diambil"))

    # Contoh 2: Bunda Nur (Anak ~4 bulan, fase ASI eksklusif, ada panggilan khusus luar jadwal)
    tgl_lahir_aisyah = (hari_ini - timedelta(days=125)).isoformat()
    cur.execute("""
        INSERT INTO users (nama_ibu, password_hash, nama_anak, tgl_lahir_anak, no_akta, poin, streak, tgl_lapor_terakhir)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Bunda Nur", hash_password("123456"), "Aisyah Putri", tgl_lahir_aisyah, "3275-LU-554433-2026", 350, 2, kemarin))
    id_nur = cur.lastrowid

    cur.execute("""
        INSERT INTO laporan_harian (user_id, tanggal, status_sehat, status_makan, status_tidur, catatan, poin_didapat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        id_nur, kemarin,
        "Sehat & Aktif",
        "Cukup (Menyusu ASI 8–12x sehari)",
        "Cukup (10–14 jam sehari, tidur nyenyak)",
        "ASI lancar setiap 2-3 jam.", 10
    ))

    # Contoh panggilan luar jadwal dari Kader untuk Bunda Nur
    cur.execute("""
        INSERT INTO panggilan_posyandu (user_id, tgl_panggilan, alasan, poin_bonus, status)
        VALUES (?, ?, ?, ?, 'Menunggu Kedatangan')
    """, (id_nur, besok, "Evaluasi berat badan & konsultasi menyusui ASI eksklusif", POIN_KUNJUNGAN_LUAR_JADWAL))


# ==============================================================================
# 4. LOGIKA BISNIS: REGISTRASI, LOGIN, POIN, STREAK, POSYANDU, PANGGILAN, & REDEEM
# ==============================================================================

def registrasi_ibu(nama_ibu: str, password: str, nama_anak: str, tgl_lahir: date, no_akta: str):
    """Mendaftarkan akun ibu baru dengan validasi usia anak maksimal 36 bulan (3 tahun)."""
    nama_ibu, nama_anak, no_akta = nama_ibu.strip(), nama_anak.strip(), no_akta.strip()

    if not nama_ibu or not password or not nama_anak or not no_akta:
        return False, "Semua kolom wajib diisi ya, Bunda."
    if len(password) < 4:
        return False, "Password minimal 4 karakter."
    if tgl_lahir > tanggal_aktif():
        return False, "Tanggal lahir anak tidak boleh di masa depan."

    tgl_lahir_str = tgl_lahir.isoformat()
    usia_bulan = hitung_usia_bulan(tgl_lahir_str)
    if usia_bulan > BATAS_USIA_MAKS_BULAN:
        return (
            False,
            f"Program BundaPoin khusus anak usia 0–3 tahun / maksimal {BATAS_USIA_MAKS_BULAN} bulan "
            f"(usia anak saat ini: {usia_bulan} bulan).",
        )

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (nama_ibu, password_hash, nama_anak, tgl_lahir_anak, no_akta, poin, streak)
            VALUES (?, ?, ?, ?, ?, 0, 0)
        """, (nama_ibu, hash_password(password), nama_anak, tgl_lahir_str, no_akta))
        conn.commit()
        return True, "Registrasi berhasil! Silakan masuk menggunakan akun Bunda."
    except sqlite3.IntegrityError:
        return False, "Nama Ibu atau Nomor Akta Kelahiran sudah terdaftar."
    finally:
        conn.close()


def verifikasi_login_ibu(nama_ibu: str, password: str):
    """Mengecek login ibu berdasarkan nama dan hash password."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE LOWER(nama_ibu) = LOWER(?) AND password_hash = ?",
        (nama_ibu.strip(), hash_password(password)),
    )
    user = cur.fetchone()
    conn.close()
    return dict(user) if user else None


def ambil_data_ibu(user_id: int):
    """Mengambil data ibu berdasarkan ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return dict(user) if user else None


def cek_sudah_lapor_hari_ini(user_id: int) -> bool:
    """Mengecek apakah ibu sudah lapor pada tanggal aktif."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM laporan_harian WHERE user_id = ? AND tanggal = ?",
        (user_id, tanggal_aktif().isoformat()),
    )
    ada = cur.fetchone() is not None
    conn.close()
    return ada


def cek_sudah_posyandu_bulan_ini(user_id: int) -> bool:
    """Mengecek apakah anak sudah kunjungan Posyandu pada bulan aktif."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM kunjungan_posyandu WHERE user_id = ? AND bulan_tahun = ?",
        (user_id, tanggal_aktif().strftime("%Y-%m")),
    )
    ada = cur.fetchone() is not None
    conn.close()
    return ada


def ambil_panggilan_aktif_ibu(user_id: int):
    """Mengambil daftar panggilan khusus Posyandu (luar jadwal) yang masih menunggu kedatangan Ibu."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM panggilan_posyandu
        WHERE user_id = ? AND status = 'Menunggu Kedatangan'
        ORDER BY tgl_panggilan ASC
    """, (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def simpan_laporan_harian(user_id: int, sehat: str, makan: str, tidur: str, catatan: str):
    """Menyimpan laporan harian, menghitung streak, dan menambah poin (+10 dan bonus +30 tiap 7 hari)."""
    if cek_sudah_lapor_hari_ini(user_id):
        return False, "Bunda sudah mengisi laporan hari ini. Kembali lagi besok ya!"

    hari_ini = tanggal_aktif()
    hari_ini_str = hari_ini.isoformat()
    kemarin_str = (hari_ini - timedelta(days=1)).isoformat()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT poin, streak, tgl_lapor_terakhir FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()

    streak_baru = (user["streak"] + 1) if user["tgl_lapor_terakhir"] == kemarin_str else 1
    poin_didapat = POIN_LAPOR_HARIAN
    dapat_bonus = False

    if streak_baru > 0 and (streak_baru % TARGET_STREAK_HARI == 0):
        poin_didapat += POIN_BONUS_STREAK
        dapat_bonus = True

    cur.execute("""
        INSERT INTO laporan_harian (user_id, tanggal, status_sehat, status_makan, status_tidur, catatan, poin_didapat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, hari_ini_str, sehat, makan, tidur, catatan.strip(), poin_didapat))

    cur.execute("""
        UPDATE users SET poin = ?, streak = ?, tgl_lapor_terakhir = ? WHERE id = ?
    """, (user["poin"] + poin_didapat, streak_baru, hari_ini_str, user_id))

    conn.commit()
    conn.close()

    pesan = f"Laporan disimpan! Bunda mendapat +{POIN_LAPOR_HARIAN} poin."
    if dapat_bonus:
        pesan += f" 🎉 Bonus Streak {streak_baru} hari: +{POIN_BONUS_STREAK} poin!"
    return True, pesan


def tukar_hadiah(user_id: int, nama_hadiah: str, harga_poin: int):
    """Mengurangi poin ibu dan menyimpan klaim hadiah dengan Kode Klaim Acak."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT poin FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()

    if not user or user["poin"] < harga_poin:
        conn.close()
        return False, "Maaf, poin Bunda belum cukup."

    waktu_str = f"{tanggal_aktif().isoformat()} {datetime.now().strftime('%H:%M')}"
    kode_klaim_acak = buat_kode_redeem_acak(user_id, nama_hadiah)

    cur.execute("UPDATE users SET poin = ? WHERE id = ?", (user["poin"] - harga_poin, user_id))
    cur.execute("""
        INSERT INTO riwayat_penukaran (user_id, kode_klaim, tanggal, nama_hadiah, poin_dipakai, status_ambil)
        VALUES (?, ?, ?, ?, ?, 'Belum Diambil')
    """, (user_id, kode_klaim_acak, waktu_str, nama_hadiah, harga_poin))

    conn.commit()
    conn.close()
    return True, f"Berhasil menukar '{nama_hadiah}' (-{harga_poin} poin). Kode Klaim Rahasia: {kode_klaim_acak} (Hanya Bunda & Kader Posyandu yang tahu kode ini)."


def verifikasi_redeem_kader(penukaran_id: int, status_baru: str = "Sudah Diberikan"):
    """Fungsi khusus Kader untuk mengubah status hadiah menjadi 'Sudah Diberikan' atau 'Belum Diambil'."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT kode_klaim FROM riwayat_penukaran WHERE id = ?", (penukaran_id,))
    row = cur.fetchone()
    kode_tampil = row["kode_klaim"] if (row and row["kode_klaim"]) else f"#RDM-{penukaran_id}"

    cur.execute(
        "UPDATE riwayat_penukaran SET status_ambil = ? WHERE id = ?",
        (status_baru, penukaran_id),
    )
    conn.commit()
    conn.close()
    return True, f"Status klaim {kode_tampil} berhasil diubah menjadi: {status_baru}!"


def simpan_kunjungan_posyandu(
    user_id: int,
    jenis_kunjungan: str,
    berat_kg: float,
    tinggi_cm: float,
    datang: bool,
    imunisasi: bool,
    naik_kurva: bool,
    catatan_kader: str,
):
    """Menyimpan verifikasi kunjungan Posyandu (Rutin Bulanan / Panggilan Luar Jadwal) dan menambah poin Ibu."""
    poin_tambahan = (
        (POIN_DATANG_POSYANDU if datang else 0)
        + (POIN_IMUNISASI_JADWAL if imunisasi else 0)
        + (POIN_BERAT_NAIK_KURVA if naik_kurva else 0)
    )
    if jenis_kunjungan == "Panggilan Khusus (Luar Jadwal)":
        poin_tambahan += POIN_KUNJUNGAN_LUAR_JADWAL

    hari_ini = tanggal_aktif()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO kunjungan_posyandu
        (user_id, tanggal, bulan_tahun, jenis_kunjungan, berat_kg, tinggi_cm, datang_posyandu, imunisasi_jadwal, berat_naik_kurva, poin_didapat, catatan_kader)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, hari_ini.isoformat(), hari_ini.strftime("%Y-%m"), jenis_kunjungan,
        berat_kg, tinggi_cm, int(datang), int(imunisasi), int(naik_kurva), poin_tambahan, catatan_kader.strip()
    ))
    cur.execute("UPDATE users SET poin = poin + ? WHERE id = ?", (poin_tambahan, user_id))

    if jenis_kunjungan == "Panggilan Khusus (Luar Jadwal)":
        cur.execute("""
            UPDATE panggilan_posyandu
            SET status = 'Sudah Hadir (+Poin)'
            WHERE user_id = ? AND status = 'Menunggu Kedatangan'
        """, (user_id,))

    conn.commit()
    conn.close()
    return True, f"Data Posyandu ({jenis_kunjungan}) disimpan! Ibu mendapat +{poin_tambahan} poin."


def buat_panggilan_posyandu(user_id: int, tgl_panggilan: date, alasan: str):
    """Membuat panggilan khusus dari Kader agar salah satu Ibu berkunjung ke Posyandu di luar jadwal rutin."""
    alasan = alasan.strip()
    if not alasan:
        return False, "Alasan pemanggilan wajib diisi oleh Kader."

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO panggilan_posyandu (user_id, tgl_panggilan, alasan, poin_bonus, status)
        VALUES (?, ?, ?, ?, 'Menunggu Kedatangan')
    """, (user_id, tgl_panggilan.isoformat(), alasan, POIN_KUNJUNGAN_LUAR_JADWAL))
    conn.commit()
    conn.close()
    return True, f"Panggilan luar jadwal berhasil dikirim ke akun Ibu (Bonus +{POIN_KUNJUNGAN_LUAR_JADWAL} poin saat hadir)!"


def verifikasi_hadir_panggilan_kader(panggilan_id: int):
    """Memverifikasi kehadiran Ibu atas panggilan khusus Kader (luar jadwal) dan langsung memberikan poin bonus."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM panggilan_posyandu WHERE id = ?", (panggilan_id,))
    panggilan = cur.fetchone()

    if not panggilan:
        conn.close()
        return False, "Data panggilan tidak ditemukan."
    if panggilan["status"] != "Menunggu Kedatangan":
        conn.close()
        return False, "Panggilan ini sudah diverifikasi sebelumnya."

    poin_bonus = panggilan["poin_bonus"]
    cur.execute("UPDATE panggilan_posyandu SET status = 'Sudah Hadir (+Poin)' WHERE id = ?", (panggilan_id,))
    cur.execute("UPDATE users SET poin = poin + ? WHERE id = ?", (poin_bonus, panggilan["user_id"]))
    conn.commit()
    conn.close()
    return True, f"Kehadiran luar jadwal diverifikasi! Ibu mendapat tambahan +{poin_bonus} poin."


# ==============================================================================
# 5. FUNGSI DEVELOPER TOOLS & KALENDER PENGINGAT (TABEL)
# ==============================================================================

def dev_reset_laporan_hari_ini(user_id: int):
    """Menghapus laporan pada tanggal aktif agar bisa didemokan submit ulang."""
    tgl_str = tanggal_aktif().isoformat()
    kemarin_str = (tanggal_aktif() - timedelta(days=1)).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT poin_didapat FROM laporan_harian WHERE user_id = ? AND tanggal = ?", (user_id, tgl_str))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM laporan_harian WHERE user_id = ? AND tanggal = ?", (user_id, tgl_str))
        cur.execute("""
            UPDATE users
            SET poin = MAX(0, poin - ?),
                streak = MAX(0, streak - 1),
                tgl_lapor_terakhir = ?
            WHERE id = ?
        """, (row["poin_didapat"], kemarin_str, user_id))
        conn.commit()
        conn.close()
        return True, f"Laporan tanggal {tgl_str} berhasil di-reset!"
    conn.close()
    return False, f"Belum ada laporan pada tanggal {tgl_str}."


def dev_reset_seluruh_database():
    """Menghapus seluruh isi tabel dan mengisi ulang dengan data contoh (seed) awal."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM laporan_harian")
    cur.execute("DELETE FROM kunjungan_posyandu")
    cur.execute("DELETE FROM riwayat_penukaran")
    cur.execute("DELETE FROM panggilan_posyandu")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM sqlite_sequence")
    isi_data_contoh(cur)
    conn.commit()
    conn.close()


def tampilkan_kalender_pengingat(user_id: int):
    """
    Menampilkan kalender pengingat berbentuk tabel di bawah laporan harian Ibu:
    - Menandai hari yang sudah lapor (✅), hari aktif saat ini (📍),
      jadwal rutin Posyandu tanggal 10 (🏥), dan tanggal panggilan luar jadwal (📢).
    """
    hari_ini = tanggal_aktif()
    tahun, bulan = hari_ini.year, hari_ini.month
    nama_bulan_id = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ][bulan]

    conn = get_connection()
    cur = conn.cursor()
    prefix_bulan = f"{tahun:04d}-{bulan:02d}-%"

    cur.execute("SELECT tanggal FROM laporan_harian WHERE user_id = ? AND tanggal LIKE ?", (user_id, prefix_bulan))
    tgl_sudah_lapor = {int(r["tanggal"].split("-")[2]) for r in cur.fetchall()}

    cur.execute("""
        SELECT tgl_panggilan FROM panggilan_posyandu
        WHERE user_id = ? AND status = 'Menunggu Kedatangan' AND tgl_panggilan LIKE ?
    """, (user_id, prefix_bulan))
    tgl_panggilan_kader = {int(r["tgl_panggilan"].split("-")[2]) for r in cur.fetchall()}
    conn.close()

    cal = calendar.Calendar(firstweekday=0)  # Senin sebagai awal minggu
    minggu_list = cal.monthdayscalendar(tahun, bulan)

    html_cal = f"""
    <div class="cal-card">
        <div class="cal-title">🗓️ Tabel Kalender Pengingat Laporan & Posyandu — {nama_bulan_id} {tahun}</div>
        <table class="cal-table">
            <thead>
                <tr>
                    <th>Sen</th><th>Sel</th><th>Rab</th><th>Kam</th><th>Jum</th><th>Sab</th><th>Min</th>
                </tr>
            </thead>
            <tbody>
    """

    for minggu in minggu_list:
        html_cal += "<tr>"
        for tgl in minggu:
            if tgl == 0:
                html_cal += "<td class='cal-empty'></td>"
            else:
                kelas = ["cal-day"]
                ikon = ""
                if tgl == hari_ini.day:
                    kelas.append("cal-today")
                    ikon += "📍"
                if tgl in tgl_sudah_lapor:
                    kelas.append("cal-reported")
                    ikon += "✅"
                if tgl == TANGGAL_RUTIN_POSYANDU:
                    kelas.append("cal-posyandu")
                    ikon += "🏥"
                if tgl in tgl_panggilan_kader:
                    kelas.append("cal-call")
                    ikon += "📢"

                html_cal += f"<td class='{' '.join(kelas)}'><div class='cal-num'>{tgl}</div><div class='cal-ico'>{ikon}</div></td>"
        html_cal += "</tr>"

    html_cal += """
            </tbody>
        </table>
        <div class="cal-legend">
            <span>📍 Hari Aktif</span>
            <span>✅ Sudah Lapor Harian</span>
            <span>🏥 Jadwal Rutin Posyandu (Tgl 10)</span>
            <span>📢 Panggilan Khusus Kader</span>
        </div>
    </div>
    """
    st.markdown(html_cal, unsafe_allow_html=True)


def tampilkan_panel_samping_dan_devtools():
    """
    Panel tambahan di Sidebar untuk:
    1. Auto Dark Mode (berdasarkan jam lokal) + Toggle Manual Tema
    2. Developer Tools (ganti hari/tanggal simulasi, reset laporan, tambah poin/streak, reset DB untuk demo)
    """
    with st.sidebar:
        st.markdown("### 🎨 Tema Tampilan")
        jam_sekarang = jam_lokal_aktif()
        status_waktu = "Malam (Auto Gelap)" if (jam_sekarang >= 18 or jam_sekarang < 6) else "Siang (Auto Terang)"
        st.caption(f"🕒 Jam Lokal Aktif: **{jam_sekarang:02d}:00** ({status_waktu})")

        st.radio(
            "Pilih Mode Tema:",
            options=["Otomatis (Jam Lokal)", "☀️ Terang", "🌙 Gelap"],
            key="mode_tema",
            help="Mode Otomatis akan mengaktifkan tema gelap pada pukul 18:00–05:59 waktu lokal pengguna.",
        )

        st.divider()
        st.markdown("### 🛠️ Developer Tools (Demo)")
        st.caption(f"📅 Tanggal Aplikasi: **{tanggal_aktif().strftime('%d-%m-%Y')}**")

        # 1. Ganti Hari / Simulasi Tanggal
        kol_m1, kol_r, kol_p1 = st.columns(3)
        with kol_m1:
            if st.button("⏪ -1 Hr", use_container_width=True, help="Mundurkan 1 hari"):
                st.session_state["dev_offset_hari"] = st.session_state.get("dev_offset_hari", 0) - 1
                st.rerun()
        with kol_r:
            if st.button("🔄 Hari Ini", use_container_width=True, help="Kembali ke tanggal asli hari ini"):
                st.session_state["dev_offset_hari"] = 0
                st.rerun()
        with kol_p1:
            if st.button("⏩ +1 Hr", use_container_width=True, help="Majukan 1 hari (untuk demo laporan besok & streak)"):
                st.session_state["dev_offset_hari"] = st.session_state.get("dev_offset_hari", 0) + 1
                st.rerun()

        # 2. Simulasi Jam Lokal (untuk menguji Auto Dark Mode di depan juri)
        opsi_jam = {
            "Ikuti Jam Asli Perangkat": None,
            "Simulasi Siang (10:00 WIB - Terang)": 10,
            "Simulasi Malam (20:00 WIB - Auto Gelap)": 20,
        }
        pilihan_jam = st.selectbox("Uji Jam Lokal (Auto Gelap):", options=list(opsi_jam.keys()))
        if st.session_state.get("dev_jam_simulasi") != opsi_jam[pilihan_jam]:
            st.session_state["dev_jam_simulasi"] = opsi_jam[pilihan_jam]
            st.rerun()

        # 3. Aksi Cepat untuk Akun Ibu yang Sedang Login
        if st.session_state.get("peran_login") == "ibu" and st.session_state.get("user_id"):
            uid = st.session_state["user_id"]
            st.markdown("**Aksi Cepat Akun Ibu:**")
            if st.button("🗑️ Reset Laporan Hari Ini", use_container_width=True):
                ok, msg = dev_reset_laporan_hari_ini(uid)
                if ok:
                    st.toast(msg, icon="🔄")
                    st.rerun()
                else:
                    st.warning(msg)

            k_s6, k_poin = st.columns(2)
            with k_s6:
                if st.button("🔥 Set Streak=6", use_container_width=True, help="Set streak jadi 6 hari kemarin agar saat lapor hari ini langsung dapat bonus 7 hari"):
                    kemarin_str = (tanggal_aktif() - timedelta(days=1)).isoformat()
                    conn = get_connection()
                    conn.execute("UPDATE users SET streak = 6, tgl_lapor_terakhir = ? WHERE id = ?", (kemarin_str, uid))
                    conn.commit()
                    conn.close()
                    st.toast("Streak diset ke 6 hari! Silakan isi laporan untuk demo bonus 7 hari.", icon="🔥")
                    st.rerun()
            with k_poin:
                if st.button("💰 +500 Poin", use_container_width=True, help="Tambah 500 poin instan untuk demo tukar hadiah"):
                    conn = get_connection()
                    conn.execute("UPDATE users SET poin = poin + 500 WHERE id = ?", (uid,))
                    conn.commit()
                    conn.close()
                    st.toast("Berhasil menambah +500 poin!", icon="⭐")
                    st.rerun()

        # 4. Reset Seluruh Database ke Seed Awal
        if st.button("♻️ Reset Seluruh Database Demo", use_container_width=True):
            dev_reset_seluruh_database()
            st.toast("Database berhasil di-reset ke data contoh awal!", icon="✅")
            st.rerun()


# ==============================================================================
# 6. TAMPILAN CSS KUSTOM (Mendukung Mode Terang & Mode Gelap Otomatis/Manual)
# ==============================================================================

def pasang_css_kustom():
    """Menambahkan CSS warna lembut (Terang) atau warna malam (Gelap) secara dinamis."""
    gelap = apakah_mode_gelap_aktif()

    if gelap:
        bg_app = "linear-gradient(180deg, #0F172A 0%, #1E293B 100%)"
        text_main = "#F1F5F9"
        card_bg = "#1E293B"
        card_border = "#334155"
        metric_label = "#94A3B8"
        metric_val = "#38BDF8"
        metric_sub = "#CBD5E1"
        rem_bg, rem_border, rem_text = "#3B2F1E", "#F59E0B", "#FDE68A"
        call_bg, call_border, call_text = "#3F1D24", "#F87171", "#FECACA"
        sch_bg, sch_border, sch_text = "#172554", "#60A5FA", "#BFDBFE"
        asi_bg, asi_border, asi_text = "#132F2C", "#2DD4BF", "#CCFBF1"
        cal_cell_bg = "#0F172A"
    else:
        bg_app = "linear-gradient(180deg, #F2F9F6 0%, #EDF6FA 100%)"
        text_main = "#1B4332"
        card_bg = "#FFFFFF"
        card_border = "#D5ECE6"
        metric_label = "#52796F"
        metric_val = "#1B4332"
        metric_sub = "#6B705C"
        rem_bg, rem_border, rem_text = "#FFF8E7", "#EE964B", "#5C4718"
        call_bg, call_border, call_text = "#FDECEC", "#D9534F", "#5A1E1E"
        sch_bg, sch_border, sch_text = "#EBF5FB", "#2E86C1", "#1B4F72"
        asi_bg, asi_border, asi_text = "#E6F4F1", "#2A9D8F", "#1D3557"
        cal_cell_bg = "#F8FAFC"

    st.markdown(f"""
        <style>
        .stApp {{ background: {bg_app}; color: {text_main}; }}
        .block-container {{ max-width: 760px; padding-top: 3.5rem; padding-bottom: 3rem; }}
        .hero-box {{
            background: linear-gradient(135deg, #2B8A78 0%, #3AAFA9 100%);
            color: #FFFFFF; padding: 1.25rem 1.4rem; border-radius: 16px;
            box-shadow: 0 6px 16px rgba(43, 138, 120, 0.18); margin-bottom: 1.2rem;
        }}
        .hero-box h1 {{ color: #FFFFFF !important; font-size: 1.7rem !important; margin: 0 0 0.25rem 0 !important; }}
        .hero-box p {{ margin: 0; font-size: 0.95rem; opacity: 0.95; color: #FFFFFF !important; }}
        .metric-card {{
            background: {card_bg}; border: 1px solid {card_border}; border-left: 6px solid #2B8A78;
            border-radius: 14px; padding: 1rem 1.1rem; box-shadow: 0 3px 10px rgba(0,0,0,0.06); margin-bottom: 0.85rem;
        }}
        .metric-label {{ font-size: 0.82rem; color: {metric_label}; font-weight: 600; text-transform: uppercase; }}
        .metric-value {{ font-size: 1.55rem; font-weight: 800; color: {metric_val}; margin-top: 0.15rem; }}
        .metric-sub {{ font-size: 0.8rem; color: {metric_sub}; margin-top: 0.2rem; }}
        .reminder-banner {{
            background-color: {rem_bg}; border: 1px solid {rem_border}; border-left: 6px solid {rem_border};
            color: {rem_text}; padding: 0.85rem 1rem; border-radius: 12px; margin-bottom: 0.8rem; font-size: 0.92rem;
        }}
        .call-banner {{
            background-color: {call_bg}; border: 1px solid {call_border}; border-left: 6px solid {call_border};
            color: {call_text}; padding: 0.9rem 1rem; border-radius: 12px; margin-bottom: 0.85rem; font-size: 0.92rem;
        }}
        .schedule-banner {{
            background-color: {sch_bg}; border: 1px solid {sch_border}; border-left: 6px solid {sch_border};
            color: {sch_text}; padding: 0.85rem 1rem; border-radius: 12px; margin-bottom: 0.85rem; font-size: 0.9rem;
        }}
        .asi-banner {{
            background-color: {asi_bg}; border: 1px solid {asi_border}; border-left: 6px solid {asi_border};
            color: {asi_text}; padding: 0.85rem 1rem; border-radius: 12px; margin-bottom: 0.9rem; font-size: 0.9rem;
        }}
        .reward-card {{
            background: {card_bg}; border: 1px solid {card_border}; border-radius: 14px;
            color: {text_main}; padding: 1rem 1.15rem; margin-bottom: 0.75rem; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        /* Gaya Tabel Kalender Pengingat di Bawah Laporan */
        .cal-card {{
            background: {card_bg}; border: 1px solid {card_border}; border-radius: 14px;
            padding: 1rem 1.1rem; margin-top: 1.1rem; box-shadow: 0 3px 10px rgba(0,0,0,0.05);
        }}
        .cal-title {{ font-weight: 700; font-size: 1rem; margin-bottom: 0.65rem; color: {metric_val}; }}
        .cal-table {{ width: 100%; border-collapse: separate; border-spacing: 4px; text-align: center; }}
        .cal-table th {{ font-size: 0.78rem; color: {metric_label}; padding: 4px; }}
        .cal-day {{
            background: {cal_cell_bg}; border: 1px solid {card_border}; border-radius: 8px;
            height: 46px; vertical-align: top; padding: 3px; font-size: 0.8rem;
        }}
        .cal-empty {{ background: transparent; }}
        .cal-today {{ border: 2px solid #F59E0B !important; font-weight: 800; }}
        .cal-reported {{ background: rgba(43, 138, 120, 0.18) !important; }}
        .cal-posyandu {{ border: 2px dashed #3B82F6 !important; }}
        .cal-call {{ border: 2px solid #EF4444 !important; }}
        .cal-num {{ font-size: 0.78rem; }}
        .cal-ico {{ font-size: 0.72rem; line-height: 1.1; }}
        .cal-legend {{
            display: flex; flex-wrap: wrap; gap: 12px; margin-top: 0.65rem;
            font-size: 0.78rem; color: {metric_sub};
        }}
        </style>
    """, unsafe_allow_html=True)


# ==============================================================================
# 7. HALAMAN-HALAMAN ANTARMUKA (UI PAGES)
# ==============================================================================

def halaman_login_dan_registrasi():
    """Halaman login Ibu, registrasi Ibu, dan login Kader."""
    st.markdown("""
        <div class="hero-box">
            <h1>🌱 BundaPoin</h1>
            <p>Pendamping Tumbuh Kembang Anak 0–3 Tahun (0–36 Bulan) Berbasis Poin & Verifikasi Posyandu</p>
        </div>
    """, unsafe_allow_html=True)

    tab_login_ibu, tab_daftar_ibu, tab_login_kader = st.tabs([
        "👩‍👧 Masuk (Ibu)", "📝 Daftar Akun Baru", "🏥 Masuk Kader Posyandu"
    ])

    with tab_login_ibu:
        st.subheader("Masuk ke Akun Bunda")
        with st.form("form_login_ibu"):
            nama_ibu = st.text_input("Nama Bunda", placeholder="Contoh: Bunda Maya")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Masuk Sekarang", use_container_width=True):
                user = verifikasi_login_ibu(nama_ibu, password)
                if user:
                    st.session_state["peran_login"] = "ibu"
                    st.session_state["user_id"] = user["id"]
                    st.rerun()
                else:
                    st.error("Nama Bunda atau password salah.")

        st.info(
            "💡 **Akun Demo:**\n"
            "- **Bunda Maya** (Anak ~10 bln, streak 6 hari) | Pass: `123456`\n"
            "- **Bunda Nur** (Anak ~4 bln, ASI Eksklusif, dipanggil Kader ke Posyandu) | Pass: `123456`"
        )

    with tab_daftar_ibu:
        st.subheader("Pendaftaran Ibu & Anak (0–3 Tahun / Maks. 36 Bulan)")
        with st.form("form_registrasi_ibu"):
            nama_ibu_baru = st.text_input("Nama Lengkap Bunda")
            pass_baru = st.text_input("Password", type="password")
            nama_anak_baru = st.text_input("Nama Lengkap Anak")
            hari_ini = tanggal_aktif()
            tgl_lahir_baru = st.date_input(
                "Tanggal Lahir Anak",
                value=hari_ini - timedelta(days=180),
                min_value=hari_ini - timedelta(days=1150),
                max_value=hari_ini,
            )
            no_akta_baru = st.text_input("Nomor Akta Kelahiran")
            if st.form_submit_button("Daftar Akun BundaPoin", use_container_width=True):
                sukses, pesan = registrasi_ibu(nama_ibu_baru, pass_baru, nama_anak_baru, tgl_lahir_baru, no_akta_baru)
                if sukses:
                    st.success(pesan)
                else:
                    st.error(pesan)

    with tab_login_kader:
        st.subheader("Portal Kader Posyandu")
        with st.form("form_login_kader"):
            nama_kader = st.text_input("Nama Kader", value="Kader Lestari")
            kode_kader = st.text_input("Kode Akses Kader", type="password")
            if st.form_submit_button("Masuk sebagai Kader", use_container_width=True):
                if kode_kader.strip() == KODE_LOGIN_KADER:
                    st.session_state["peran_login"] = "kader"
                    st.session_state["nama_kader"] = nama_kader.strip() or "Kader Posyandu"
                    st.rerun()
                else:
                    st.error("Kode Kader salah.")
        st.info(f"🔑 **Kode Kader Demo:** `{KODE_LOGIN_KADER}`")


def halaman_utama_ibu():
    """Dashboard Ibu: pengingat, jadwal rutin, panggilan luar jadwal, laporan harian spesifik + kalender, katalog hadiah, & riwayat."""
    user = ambil_data_ibu(st.session_state["user_id"])
    if not user:
        st.session_state.clear()
        st.rerun()

    usia_bulan = hitung_usia_bulan(user["tgl_lahir_anak"])
    sudah_lapor = cek_sudah_lapor_hari_ini(user["id"])
    sudah_posyandu = cek_sudah_posyandu_bulan_ini(user["id"])
    daftar_panggilan = ambil_panggilan_aktif_ibu(user["id"])
    jadwal_rutin_str = ambil_jadwal_rutin_berikutnya()

    kol_judul, kol_keluar = st.columns([4, 1])
    with kol_judul:
        st.markdown(f"""
            <div class="hero-box">
                <h1>Halo, {user['nama_ibu']}! 👋</h1>
                <p>Anak: <b>{user['nama_anak']}</b> ({usia_bulan} bulan) • No. Akta: {user['no_akta']}</p>
            </div>
        """, unsafe_allow_html=True)
    with kol_keluar:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🚪 Keluar", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # BANNER 1: Panggilan Khusus Kader Posyandu (Luar Jadwal) jika ada
    for p in daftar_panggilan:
        st.markdown(f"""
            <div class="call-banner">
                📢 <b>Panggilan Khusus Kader Posyandu (Luar Jadwal Rutin):</b><br>
                Bunda diminta hadir ke Posyandu pada tanggal <b>{p['tgl_panggilan']}</b> untuk:
                <i>"{p['alasan']}"</i>.<br>
                🎁 Hadir memenuhi panggilan ini akan mendapat tambahan <b>+{p['poin_bonus']} Poin</b>!
            </div>
        """, unsafe_allow_html=True)

    # BANNER 2: Jadwal Rutin Posyandu (1x Sebulan)
    status_rutin_teks = (
        "✅ Sudah hadir bulan ini"
        if sudah_posyandu
        else f"⏳ Belum hadir bulan ini (Bonus hadir hingga +{POIN_DATANG_POSYANDU + POIN_IMUNISASI_JADWAL + POIN_BERAT_NAIK_KURVA} poin)"
    )
    st.markdown(f"""
        <div class="schedule-banner">
            📅 <b>Jadwal Rutin Posyandu (1x Sebulan — Setiap Tanggal {TANGGAL_RUTIN_POSYANDU}):</b><br>
            Jadwal terdekat: <b>{jadwal_rutin_str}</b> • Status bulan ini: <b>{status_rutin_teks}</b>
        </div>
    """, unsafe_allow_html=True)

    # BANNER 3: Pengingat Laporan Harian
    if not sudah_lapor:
        st.markdown(f"""
            <div class="reminder-banner">
                ⏰ <b>Pengingat Harian:</b> Hari ini ({tanggal_aktif().strftime('%d-%m-%Y')}) Bunda belum mengisi laporan kondisi <b>{user['nama_anak']}</b> (+{POIN_LAPOR_HARIAN} poin).
            </div>
        """, unsafe_allow_html=True)

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Total Poin</div>
                <div class="metric-value">⭐ {user['poin']}</div>
                <div class="metric-sub">Bisa ditukar hadiah</div>
            </div>
        """, unsafe_allow_html=True)
    with k2:
        sisa_hari = TARGET_STREAK_HARI - (user["streak"] % TARGET_STREAK_HARI)
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Streak Saat Ini</div>
                <div class="metric-value">🔥 {user['streak']} Hari</div>
                <div class="metric-sub">{sisa_hari} hari lagi bonus +{POIN_BONUS_STREAK} poin</div>
            </div>
        """, unsafe_allow_html=True)
    with k3:
        fase = "ASI Eksklusif (0-6 bln)" if usia_bulan <= 6 else "MPASI & Gizi Anak (7-36 bln)"
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Usia Anak</div>
                <div class="metric-value">👶 {usia_bulan} Bln</div>
                <div class="metric-sub">{fase}</div>
            </div>
        """, unsafe_allow_html=True)

    tab_lapor, tab_hadiah, tab_riwayat = st.tabs([
        "📋 Laporan Harian", "🎁 Katalog Hadiah", "📊 Riwayat & Jadwal"
    ])

    with tab_lapor:
        st.subheader(f"Laporan Harian Spesifik — {user['nama_anak']}")
        if sudah_lapor:
            st.success("✅ Bunda sudah mengisi laporan pada tanggal ini. Terima kasih sudah memantau tumbuh kembang si kecil!")
        else:
            with st.form("form_lapor_harian"):
                sehat = st.radio(
                    "1. Bagaimana kondisi kesehatan anak hari ini?",
                    options=[
                        "Sehat & Aktif",
                        "Kurang Sehat (Demam / Batuk / Pilek / Diare)",
                    ],
                )

                if usia_bulan <= BATAS_USIA_ASI_EKSKLUSIF_BULAN:
                    opsi_makan = [
                        "Cukup (Menyusu ASI 8–12x sehari)",
                        "Sedang (Menyusu ASI 5–7x sehari)",
                        "Kurang (Menyusu ASI < 5x sehari)",
                    ]
                    judul_makan = "2. Berapa kali frekuensi menyusu ASI dalam sehari?"
                else:
                    opsi_makan = [
                        "Cukup (Makan 3x sehari + camilan/ASI)",
                        "Sedang (Makan 2x sehari)",
                        "Kurang (Makan ≤ 1x sehari / Gerakan Tutup Mulut)",
                    ]
                    judul_makan = "2. Berapa kali anak makan (MPASI / makanan keluarga) dalam sehari?"

                makan = st.radio(judul_makan, options=opsi_makan)

                tidur = st.radio(
                    "3. Berapa lama total waktu tidur anak sehari (tidur malam + tidur siang)?",
                    options=[
                        "Cukup (10–14 jam sehari, tidur nyenyak)",
                        "Sedang (8–9 jam sehari)",
                        "Kurang (< 8 jam sehari / sering rewel malam)",
                    ],
                )

                catatan = st.text_area(
                    "4. Catatan Tambahan Ibu (Opsional)",
                    placeholder="Contoh: Makan siang habis 1 mangkuk tim telur, tidur siang 2 jam.",
                )

                if st.form_submit_button(f"Kirim Laporan Harian (+{POIN_LAPOR_HARIAN} Poin)", use_container_width=True):
                    sukses, pesan = simpan_laporan_harian(user["id"], sehat, makan, tidur, catatan)
                    if sukses:
                        st.toast(pesan, icon="🎉")
                        st.rerun()
                    else:
                        st.warning(pesan)

        # Tabel Kalender Pengingat di bawah Laporan Harian
        tampilkan_kalender_pengingat(user["id"])

    with tab_hadiah:
        st.markdown("""
            <div class="asi-banner">
                🍼 <b>Catatan ASI Eksklusif:</b> Bayi usia <b>0–6 bulan</b> sebaiknya diberikan <b>ASI Eksklusif</b>.
                Hadiah <b>Susu / MPASI</b> hanya muncul untuk anak berusia <b>di atas 6 bulan (7–36 bulan)</b>.
            </div>
        """, unsafe_allow_html=True)

        di_atas_6_bln = usia_lebih_dari_6_bulan(user["tgl_lahir_anak"])
        for item in KATALOG_HADIAH:
            if item["harus_di_atas_6_bulan"] and not di_atas_6_bln:
                continue

            st.markdown(f"""
                <div class="reward-card">
                    <b>{item['ikon']} {item['nama']}</b> — <span style="color:#2B8A78;font-weight:700;">{item['harga']} Poin</span><br>
                    <span style="font-size:0.88rem;opacity:0.85;">{item['deskripsi']}</span>
                </div>
            """, unsafe_allow_html=True)

            cukup = user["poin"] >= item["harga"]
            label_btn = f"Tukar {item['nama']} ({item['harga']} Poin)" if cukup else f"Poin Kurang (Butuh {item['harga'] - user['poin']} lagi)"
            if st.button(label_btn, key=f"tukar_{item['id']}", disabled=not cukup, use_container_width=True):
                sukses, pesan = tukar_hadiah(user["id"], item["nama"], item["harga"])
                if sukses:
                    st.success(pesan)
                    st.rerun()
                else:
                    st.error(pesan)

    with tab_riwayat:
        conn = get_connection()

        st.markdown("#### 📢 Riwayat Panggilan Khusus Posyandu (Luar Jadwal)")
        df_panggilan_ibu = pd.read_sql_query("""
            SELECT tgl_panggilan AS "Tanggal Panggilan",
                   alasan AS "Alasan Pemanggilan Kader",
                   poin_bonus AS "Bonus Poin (+)",
                   status AS "Status Kehadiran"
            FROM panggilan_posyandu WHERE user_id = ? ORDER BY id DESC
        """, conn, params=(user["id"],))
        st.dataframe(df_panggilan_ibu, use_container_width=True, hide_index=True)

        st.markdown("#### 🎁 Riwayat Penukaran Hadiah & Kode Klaim Rahasia")
        df_tukar = pd.read_sql_query("""
            SELECT COALESCE(kode_klaim, '#RDM-' || id) AS "Kode Klaim Acak",
                   tanggal AS "Waktu",
                   nama_hadiah AS "Hadiah",
                   poin_dipakai AS "Poin (-)",
                   status_ambil AS "Status Produk"
            FROM riwayat_penukaran WHERE user_id = ? ORDER BY id DESC
        """, conn, params=(user["id"],))
        st.dataframe(df_tukar, use_container_width=True, hide_index=True)

        st.markdown("#### 📅 Riwayat Laporan Harian")
        df_lapor = pd.read_sql_query("""
            SELECT tanggal AS "Tanggal", status_sehat AS "Kesehatan", status_makan AS "Frekuensi Makan/ASI",
                   status_tidur AS "Durasi Tidur", catatan AS "Catatan", poin_didapat AS "Poin (+)"
            FROM laporan_harian WHERE user_id = ? ORDER BY tanggal DESC
        """, conn, params=(user["id"],))
        st.dataframe(df_lapor, use_container_width=True, hide_index=True)

        st.markdown("#### 🏥 Riwayat Kunjungan Posyandu")
        df_pos = pd.read_sql_query("""
            SELECT tanggal AS "Tanggal", jenis_kunjungan AS "Jenis Kunjungan",
                   berat_kg AS "Berat (kg)", tinggi_cm AS "Tinggi (cm)",
                   poin_didapat AS "Poin (+)", catatan_kader AS "Catatan Kader"
            FROM kunjungan_posyandu WHERE user_id = ? ORDER BY id DESC
        """, conn, params=(user["id"],))
        st.dataframe(df_pos, use_container_width=True, hide_index=True)
        conn.close()


def halaman_kader_posyandu():
    """Halaman Kader Posyandu: daftar ibu, input kunjungan rutin/luar jadwal, panggil ibu luar jadwal, & verifikasi redeem."""
    nama_kader = st.session_state.get("nama_kader", "Kader Posyandu")
    kol_judul, kol_keluar = st.columns([4, 1])
    with kol_judul:
        st.markdown(f"""
            <div class="hero-box">
                <h1>🏥 Dashboard Kader Posyandu</h1>
                <p>Petugas: <b>{nama_kader}</b> • Jadwal Rutin: Tanggal {TANGGAL_RUTIN_POSYANDU} Tiap Bulan ({JAM_OPERASIONAL_POSYANDU})</p>
            </div>
        """, unsafe_allow_html=True)
    with kol_keluar:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🚪 Keluar", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    conn = get_connection()
    df_ibu = pd.read_sql_query("SELECT * FROM users ORDER BY nama_ibu ASC", conn)
    df_ibu["Usia (Bln)"] = df_ibu["tgl_lahir_anak"].apply(hitung_usia_bulan)
    opsi_ibu = {r["id"]: f"{r['nama_ibu']} — {r['nama_anak']} ({r['Usia (Bln)']} bln)" for _, r in df_ibu.iterrows()}

    tab_kunjungan, tab_panggilan, tab_redeem = st.tabs([
        "✍️ Input Kunjungan Posyandu",
        "📢 Panggil Ibu (Luar Jadwal)",
        "🎁 Verifikasi Redeem Hadiah",
    ])

    # --- TAB 1: DAFTAR IBU & INPUT KUNJUNGAN POSYANDU ---
    with tab_kunjungan:
        st.subheader("📋 Daftar Ibu & Anak (0–36 Bulan)")
        st.dataframe(
            df_ibu[["nama_ibu", "nama_anak", "Usia (Bln)", "no_akta", "poin", "streak", "tgl_lapor_terakhir"]],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("✍️ Input Kunjungan Posyandu (Rutin Bulanan / Luar Jadwal)")
        with st.form("form_kunjungan_kader"):
            user_id_pilih = st.selectbox("Pilih Ibu & Anak", options=list(opsi_ibu.keys()), format_func=lambda x: opsi_ibu[x])
            jenis_kunjungan = st.radio(
                "Jenis Kunjungan Posyandu:",
                options=["Rutin Bulanan", "Panggilan Khusus (Luar Jadwal)"],
                horizontal=True,
                help=f"Jika Panggilan Khusus (Luar Jadwal), Ibu otomatis mendapat tambahan +{POIN_KUNJUNGAN_LUAR_JADWAL} poin.",
            )
            c1, c2 = st.columns(2)
            with c1:
                berat_kg = st.number_input("Berat Badan (kg)", min_value=1.5, max_value=30.0, value=8.5, step=0.1)
            with c2:
                tinggi_cm = st.number_input("Tinggi Badan (cm)", min_value=40.0, max_value=120.0, value=70.0, step=0.5)

            datang = st.checkbox(f"Datang Posyandu (+{POIN_DATANG_POSYANDU} poin)", value=True)
            imunisasi = st.checkbox(f"Imunisasi Sesuai Jadwal (+{POIN_IMUNISASI_JADWAL} poin)", value=False)
            naik_kurva = st.checkbox(f"Berat Badan Naik Sesuai Kurva (+{POIN_BERAT_NAIK_KURVA} poin)", value=True)
            catatan_kader = st.text_input("Catatan Kader")

            if st.form_submit_button("Simpan Kunjungan & Tambah Poin", use_container_width=True):
                sukses, pesan = simpan_kunjungan_posyandu(
                    user_id_pilih, jenis_kunjungan, berat_kg, tinggi_cm, datang, imunisasi, naik_kurva, catatan_kader
                )
                if sukses:
                    st.success(pesan)
                    st.rerun()

    # --- TAB 2: PANGGIL IBU BERKUNJUNG KE POSYANDU (LUAR JADWAL) ---
    with tab_panggilan:
        st.subheader("📢 Panggil Ibu ke Posyandu (Kunjungan Luar Jadwal)")
        st.caption(
            f"Gunakan fitur ini jika ada anak yang perlu dipantau khusus di luar jadwal rutin bulanan. "
            f"Saat Ibu hadir memenuhi panggilan, Ibu mendapat bonus **+{POIN_KUNJUNGAN_LUAR_JADWAL} poin**."
        )

        with st.form("form_buat_panggilan"):
            user_id_panggil = st.selectbox(
                "Pilih Ibu yang Akan Dipanggil",
                options=list(opsi_ibu.keys()),
                format_func=lambda x: opsi_ibu[x],
            )
            tgl_panggilan = st.date_input(
                "Tanggal Diminta Berkunjung ke Posyandu",
                value=tanggal_aktif() + timedelta(days=1),
                min_value=tanggal_aktif(),
            )
            alasan_panggilan = st.text_input(
                "Alasan Pemanggilan / Keperluan Pemeriksaan",
                placeholder="Contoh: Pemantauan berat badan kurang / pemberian vitamin A susulan / konseling MPASI",
            )
            if st.form_submit_button(f"Kirim Panggilan ke Ibu (Bonus +{POIN_KUNJUNGAN_LUAR_JADWAL} Poin)", use_container_width=True):
                sukses, pesan = buat_panggilan_posyandu(user_id_panggil, tgl_panggilan, alasan_panggilan)
                if sukses:
                    st.success(pesan)
                    st.rerun()
                else:
                    st.error(pesan)

        st.markdown("#### 📋 Daftar Panggilan Luar Jadwal & Verifikasi Kehadiran")
        df_panggilan = pd.read_sql_query("""
            SELECT p.id,
                   p.tgl_panggilan AS "Tgl Panggilan",
                   u.nama_ibu AS "Nama Ibu",
                   u.nama_anak AS "Nama Anak",
                   p.alasan AS "Alasan Pemanggilan",
                   p.poin_bonus AS "Bonus Poin (+)",
                   p.status AS "Status"
            FROM panggilan_posyandu p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.id DESC
        """, conn)

        if df_panggilan.empty:
            st.info("Belum ada panggilan luar jadwal.")
        else:
            st.dataframe(df_panggilan.drop(columns=["id"]), use_container_width=True, hide_index=True)

            df_menunggu = df_panggilan[df_panggilan["Status"] == "Menunggu Kedatangan"]
            if not df_menunggu.empty:
                with st.form("form_verifikasi_panggilan"):
                    opsi_panggilan = {
                        r["id"]: f"#{r['id']} | {r['Nama Ibu']} ({r['Tgl Panggilan']}) — {r['Alasan Pemanggilan']}"
                        for _, r in df_menunggu.iterrows()
                    }
                    id_panggilan_hadir = st.selectbox(
                        "Pilih Panggilan yang Sudah Dihadiri Ibu",
                        options=list(opsi_panggilan.keys()),
                        format_func=lambda x: opsi_panggilan[x],
                    )
                    if st.form_submit_button(
                        f"Verifikasi Ibu Sudah Hadir (+{POIN_KUNJUNGAN_LUAR_JADWAL} Poin)",
                        use_container_width=True,
                    ):
                        sukses, pesan = verifikasi_hadir_panggilan_kader(id_panggilan_hadir)
                        if sukses:
                            st.success(pesan)
                            st.rerun()
                        else:
                            st.error(pesan)

    # --- TAB 3: VERIFIKASI REDEEM HADIAH ---
    with tab_redeem:
        st.subheader("🎁 Verifikasi Redeem Hadiah (Kode Klaim Acak)")
        df_klaim = pd.read_sql_query("""
            SELECT r.id,
                   COALESCE(r.kode_klaim, '#RDM-' || r.id) AS "Kode Klaim Acak",
                   r.tanggal AS "Tanggal Tukar",
                   u.nama_ibu AS "Nama Ibu",
                   r.nama_hadiah AS "Produk Hadiah",
                   r.poin_dipakai AS "Poin",
                   r.status_ambil AS "Status Produk"
            FROM riwayat_penukaran r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.id DESC
        """, conn)

        if df_klaim.empty:
            st.info("Belum ada penukaran hadiah.")
        else:
            st.dataframe(df_klaim.drop(columns=["id"]), use_container_width=True, hide_index=True)
            with st.form("form_redeem_kader"):
                opsi_klaim = {
                    r["id"]: f"{r['Kode Klaim Acak']} | {r['Nama Ibu']} — {r['Produk Hadiah']} [{r['Status Produk']}]"
                    for _, r in df_klaim.iterrows()
                }
                id_klaim = st.selectbox("Pilih Kode Klaim Hadiah Ibu", options=list(opsi_klaim.keys()), format_func=lambda x: opsi_klaim[x])
                status_baru = st.radio("Status Produk Fisik:", ["Sudah Diberikan", "Belum Diambil"], horizontal=True)
                if st.form_submit_button("Update Status Produk", use_container_width=True):
                    sukses, pesan = verifikasi_redeem_kader(id_klaim, status_baru)
                    if sukses:
                        st.success(pesan)
                        st.rerun()

    conn.close()


# ==============================================================================
# 8. MAIN ENTRY POINT
# ==============================================================================

def main():
    st.set_page_config(
        page_title="BundaPoin",
        page_icon="🌱",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    if "peran_login" not in st.session_state:
        st.session_state["peran_login"] = None
    if "dev_offset_hari" not in st.session_state:
        st.session_state["dev_offset_hari"] = 0
    if "mode_tema" not in st.session_state:
        st.session_state["mode_tema"] = "Otomatis (Jam Lokal)"

    init_db()
    tampilkan_panel_samping_dan_devtools()
    pasang_css_kustom()

    if st.session_state["peran_login"] == "ibu":
        halaman_utama_ibu()
    elif st.session_state["peran_login"] == "kader":
        halaman_kader_posyandu()
    else:
        halaman_login_dan_registrasi()


if __name__ == "__main__":
    main()