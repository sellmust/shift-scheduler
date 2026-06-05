"""
db.py — Semua operasi database (PostgreSQL)

Aturan jadwal:
  BARISTA (4 orang, 1/slot) : min 3 shift, 2 orang dapat 4 (bergantian)
  KITCHEN (7 orang, 2/slot) : min 3 shift, maks 5, partner selalu beda
  Min availability           : 5 slot — kalau kurang, generate dibatalkan
"""

import os, random, json
from datetime import date, timedelta
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

HARI_ORDER  = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
MIN_AVAIL   = 6  # minimal 6 hari berbeda
# Barista: 3 orang, 14 total slot → 2 orang dapat 5, 1 orang dapat 4
BARISTA_TOTAL = 14   # 7 hari × 2 sesi × 1 orang
BARISTA_HIGH  = 5    # shift lebih banyak
BARISTA_LOW   = 4    # shift lebih sedikit
# Kitchen: 5 orang, 28 total slot → 3 orang dapat 6, 2 orang dapat 5
KITCHEN_TOTAL = 28   # 7 hari × 2 sesi × 2 orang
KITCHEN_HIGH  = 6    # shift lebih banyak
KITCHEN_LOW   = 5    # shift lebih sedikit
MIN_SHIFT   = 3
MAX_SHIFT_K = 6  # kitchen maks 6 shift
BULAN_NAMA  = ['','Januari','Februari','Maret','April','Mei','Juni',
               'Juli','Agustus','September','Oktober','November','Desember']


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# ═══════════════════════════════════════════════════════════
# HELPERS TANGGAL
# ═══════════════════════════════════════════════════════════

def get_tanggal_minggu(senin: date) -> dict:
    return {HARI_ORDER[i]: senin + timedelta(days=i) for i in range(7)}


def format_rentang(senin: date) -> str:
    minggu = senin + timedelta(days=6)
    if senin.month == minggu.month:
        return f"{senin.day}–{minggu.day} {BULAN_NAMA[senin.month]} {senin.year}"
    return f"{senin.day} {BULAN_NAMA[senin.month]}–{minggu.day} {BULAN_NAMA[minggu.month]} {senin.year}"


# ═══════════════════════════════════════════════════════════
# KARYAWAN
# ═══════════════════════════════════════════════════════════

def get_or_create_karyawan(nama: str, bagian: str = None) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, nama, bagian FROM karyawan WHERE LOWER(nama)=LOWER(%s)", (nama,))
            row = cur.fetchone()
            if row:
                return dict(row)
            if not bagian:
                return None
            cur.execute(
                "INSERT INTO karyawan (nama, bagian) VALUES (%s,%s) RETURNING id, nama, bagian",
                (nama, bagian)
            )
            return dict(cur.fetchone())


def get_all_karyawan() -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, nama, bagian FROM karyawan ORDER BY bagian, nama")
            return [dict(r) for r in cur.fetchall()]


def get_karyawan_by_bagian(bagian: str) -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, nama FROM karyawan WHERE bagian=%s ORDER BY nama", (bagian,))
            return [dict(r) for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════
# AVAILABILITY
# ═══════════════════════════════════════════════════════════

def upsert_availability(karyawan_id: int, slots: list[dict]) -> int:
    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for slot in slots:
                cur.execute(
                    """INSERT INTO availability (karyawan_id, hari, sesi)
                       VALUES (%s,%s,%s) ON CONFLICT (karyawan_id, hari, sesi) DO NOTHING""",
                    (karyawan_id, slot["hari"], slot["sesi"])
                )
                if cur.rowcount > 0:
                    inserted += 1
    return inserted


def get_availability_per_karyawan() -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT k.id, k.nama, k.bagian,
                       COUNT(a.id) AS total,
                       COUNT(DISTINCT a.hari) AS total_hari,
                       CASE WHEN COUNT(DISTINCT a.hari) >= 6 THEN true ELSE false END AS cukup
                FROM karyawan k
                LEFT JOIN availability a ON a.karyawan_id = k.id
                GROUP BY k.id, k.nama, k.bagian
                ORDER BY k.bagian, k.nama
            """)
            return [dict(r) for r in cur.fetchall()]


def get_availability_summary() -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.hari, a.sesi, k.bagian,
                       ARRAY_AGG(json_build_object('id',k.id,'nama',k.nama) ORDER BY k.nama) AS karyawan
                FROM availability a
                JOIN karyawan k ON a.karyawan_id = k.id
                GROUP BY a.hari, a.sesi, k.bagian
                ORDER BY
                    ARRAY_POSITION(ARRAY['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']::VARCHAR[], a.hari),
                    CASE a.sesi WHEN 'Pagi' THEN 1 ELSE 2 END, k.bagian
            """)
            return [dict(r) for r in cur.fetchall()]


def reset_availability_karyawan(karyawan_id: int):
    """Hapus SEMUA availability 1 karyawan."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM availability WHERE karyawan_id=%s", (karyawan_id,))


def hapus_slot_availability(karyawan_id: int, hari: str, sesi: str) -> bool:
    """Hapus 1 slot availability tertentu. Return True kalau berhasil."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM availability WHERE karyawan_id=%s AND hari=%s AND sesi=%s",
                (karyawan_id, hari, sesi)
            )
            return cur.rowcount > 0


def get_availability_karyawan(karyawan_id: int) -> list:
    """Ambil semua slot availability 1 karyawan."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT hari, sesi FROM availability
                   WHERE karyawan_id=%s
                   ORDER BY
                     ARRAY_POSITION(ARRAY['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']::VARCHAR[], hari),
                     CASE sesi WHEN 'Pagi' THEN 1 ELSE 2 END""",
                (karyawan_id,)
            )
            return [dict(r) for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════
# GENERATE JADWAL — helpers
# ═══════════════════════════════════════════════════════════

def build_avail_map(bagian: str) -> dict:
    avail_map = {(h, s): [] for h in HARI_ORDER for s in ['Pagi','Sore']}
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.hari, a.sesi, k.id AS kid
                FROM availability a JOIN karyawan k ON a.karyawan_id=k.id
                WHERE k.bagian=%s
            """, (bagian,))
            for r in cur.fetchall():
                avail_map[(r["hari"], r["sesi"])].append(r["kid"])
    return avail_map


def get_barista_high_last_week(minggu: date) -> list[int]:
    """Ambil id barista yang dapat shift BANYAK (5) minggu lalu → minggu ini dapat sedikit (4)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT DISTINCT minggu FROM jadwal WHERE minggu<%s ORDER BY minggu DESC LIMIT 1", (minggu,))
            row = cur.fetchone()
            if not row:
                return []
            cur.execute("""
                SELECT karyawan_id FROM jadwal j
                JOIN karyawan k ON j.karyawan_id=k.id
                WHERE j.minggu=%s AND k.bagian='barista'
                GROUP BY karyawan_id HAVING COUNT(*)>=5
            """, (row["minggu"],))
            return [r["karyawan_id"] for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════
# GENERATE JADWAL — barista & kitchen
# ═══════════════════════════════════════════════════════════

def _generate_barista(minggu: date, tanggal_map: dict) -> tuple[list, list]:
    karyawan  = get_karyawan_by_bagian('barista')
    avail_map = build_avail_map('barista')
    warnings  = []
    nama_map  = {k["id"]: k["nama"] for k in karyawan}
    semua_ids = [k["id"] for k in karyawan]

    # Validasi min 6 hari berbeda
    count_avail = {}
    for kid in semua_ids:
        hari_set = set(h for (h, s), ids in avail_map.items() if kid in ids)
        count_avail[kid] = len(hari_set)
    kurang = [nama_map[kid] for kid in semua_ids if count_avail.get(kid, 0) < MIN_AVAIL]
    if kurang:
        raise ValueError(f"Barista belum setor min {MIN_AVAIL} hari availability: {', '.join(kurang)}")

    # Rotasi: yang minggu lalu dapat 5 (HIGH) → minggu ini dapat 4 (LOW)
    # Barista 3 orang: 2 orang dapat 5, 1 orang dapat 4
    dapat_high_lalu = set(get_barista_high_last_week(minggu))
    if dapat_high_lalu:
        # Yang dapat banyak minggu lalu → sekarang dapat sedikit
        pool_low = list(dapat_high_lalu)
        pool_high = [k for k in semua_ids if k not in dapat_high_lalu]
    else:
        # Pertama kali → acak
        pool_all = semua_ids[:]
        random.shuffle(pool_all)
        pool_low  = pool_all[:1]   # 1 orang dapat 4
        pool_high = pool_all[1:]   # 2 orang dapat 5

    target      = {kid: BARISTA_LOW if kid in pool_low else BARISTA_HIGH for kid in semua_ids}
    assigned    = {kid: 0 for kid in semua_ids}
    hari_sudah  = {kid: set() for kid in semua_ids}  # tracking hari yang sudah dipakai

    all_slots = sorted([(h,s) for h in HARI_ORDER for s in ['Pagi','Sore']], key=lambda hs: len(avail_map[hs]))

    rows = []
    for (hari, sesi) in all_slots:
        kandidat = avail_map[(hari, sesi)]
        if not kandidat:
            warnings.append(f"Barista: tidak ada yang available {hari} {sesi}")
            continue
        # Filter: belum capai target DAN belum kerja di hari ini
        bisa = [k for k in kandidat if assigned[k] < target[k] and hari not in hari_sudah[k]]
        if not bisa:
            # Fallback: minimal belum kerja hari ini
            bisa = [k for k in kandidat if hari not in hari_sudah[k]]
        if not bisa:
            warnings.append(f"Barista: semua yang available {hari} sudah punya shift hari itu")
            continue
        bisa.sort(key=lambda k: assigned[k])
        terpilih = bisa[0]
        assigned[terpilih] += 1
        hari_sudah[terpilih].add(hari)
        rows.append({
            "hari": hari, "sesi": sesi, "bagian": "barista",
            "tanggal": tanggal_map[hari],
            "karyawan_id": terpilih, "nama": nama_map[terpilih]
        })

    for kid, total in assigned.items():
        if total < MIN_SHIFT:
            warnings.append(f"Barista {nama_map[kid]} hanya {total} shift (min {BARISTA_LOW})")

    return rows, warnings


def _generate_kitchen(minggu: date, tanggal_map: dict) -> tuple[list, list]:
    karyawan  = get_karyawan_by_bagian('kitchen')
    avail_map = build_avail_map('kitchen')
    warnings  = []
    nama_map  = {k["id"]: k["nama"] for k in karyawan}
    semua_ids = [k["id"] for k in karyawan]

    # Validasi min 6 hari berbeda
    count_avail = {}
    for kid in semua_ids:
        hari_set = set(h for (h, s), ids in avail_map.items() if kid in ids)
        count_avail[kid] = len(hari_set)
    kurang = [nama_map[kid] for kid in semua_ids if count_avail.get(kid, 0) < MIN_AVAIL]
    if kurang:
        raise ValueError(f"Kitchen belum setor min {MIN_AVAIL} hari availability: {', '.join(kurang)}")

    # Rotasi kitchen: yang dapat 6 minggu lalu → minggu ini dapat 5
    # Kitchen 5 orang: 3 orang dapat 6, 2 orang dapat 5
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT DISTINCT minggu FROM jadwal WHERE minggu<%s ORDER BY minggu DESC LIMIT 1", (minggu,))
            row_last = cur.fetchone()
            dapat_high_k_lalu = set()
            if row_last:
                cur.execute("""
                    SELECT karyawan_id FROM jadwal j
                    JOIN karyawan k ON j.karyawan_id=k.id
                    WHERE j.minggu=%s AND k.bagian='kitchen'
                    GROUP BY karyawan_id HAVING COUNT(*)>=6
                """, (row_last["minggu"],))
                dapat_high_k_lalu = {r["karyawan_id"] for r in cur.fetchall()}

    if dapat_high_k_lalu:
        pool_low_k  = list(dapat_high_k_lalu)[:2]
        pool_high_k = [k for k in semua_ids if k not in set(pool_low_k)]
    else:
        pool_all_k = semua_ids[:]
        random.shuffle(pool_all_k)
        pool_low_k  = pool_all_k[:2]   # 2 orang dapat 5
        pool_high_k = pool_all_k[2:]   # 3 orang dapat 6

    target_k = {kid: KITCHEN_LOW if kid in pool_low_k else KITCHEN_HIGH for kid in semua_ids}
    assigned        = {kid: 0 for kid in semua_ids}
    partner_history = {kid: set() for kid in semua_ids}
    hari_sudah_k    = {kid: set() for kid in semua_ids}  # tracking hari yang sudah dipakai

    all_slots = sorted([(h,s) for h in HARI_ORDER for s in ['Pagi','Sore']], key=lambda hs: len(avail_map[hs]))

    rows = []
    for (hari, sesi) in all_slots:
        kandidat = avail_map[(hari, sesi)]
        if not kandidat:
            warnings.append(f"Kitchen: tidak ada yang available {hari} {sesi}")
            continue

        # Filter: belum kerja di hari ini
        kandidat_free = [k for k in kandidat if hari not in hari_sudah_k[k]]

        if len(kandidat_free) == 0:
            warnings.append(f"Kitchen {hari} {sesi}: semua yang available sudah punya shift hari itu")
            continue
        if len(kandidat_free) == 1:
            warnings.append(f"Kitchen {hari} {sesi}: hanya 1 orang available (belum kerja hari ini)")
            kid = kandidat_free[0]
            assigned[kid] += 1
            hari_sudah_k[kid].add(hari)
            rows.append({"hari": hari, "sesi": sesi, "bagian": "kitchen",
                         "tanggal": tanggal_map[hari], "karyawan_id": kid, "nama": nama_map[kid]})
            continue

        bisa = [k for k in kandidat_free if assigned[k] < target_k.get(k, KITCHEN_HIGH)] or sorted(kandidat_free, key=lambda k: assigned[k])
        pasangan = []
        for i, k1 in enumerate(bisa):
            for k2 in bisa[i+1:]:
                pasangan.append((int(k2 in partner_history[k1]), assigned[k1]+assigned[k2], k1, k2))
        pasangan.sort()
        _, _, kid1, kid2 = pasangan[0] if pasangan else (0, 0, bisa[0], bisa[1])

        partner_history[kid1].add(kid2)
        partner_history[kid2].add(kid1)
        for kid in [kid1, kid2]:
            assigned[kid] += 1
            hari_sudah_k[kid].add(hari)
            rows.append({"hari": hari, "sesi": sesi, "bagian": "kitchen",
                         "tanggal": tanggal_map[hari], "karyawan_id": kid, "nama": nama_map[kid]})

    for kid, total in assigned.items():
        if total < MIN_SHIFT:
            warnings.append(f"Kitchen {nama_map[kid]} hanya {total} shift (min {KITCHEN_LOW})")

    return rows, warnings


# ═══════════════════════════════════════════════════════════
# GENERATE & SAVE (entry point)
# ═══════════════════════════════════════════════════════════

def generate_and_save_jadwal(minggu_str: str) -> dict:
    minggu      = date.fromisoformat(minggu_str)
    tanggal_map = get_tanggal_minggu(minggu)
    rentang     = format_rentang(minggu)

    b_rows, b_warn = _generate_barista(minggu, tanggal_map)
    k_rows, k_warn = _generate_kitchen(minggu, tanggal_map)

    all_rows = b_rows + k_rows
    all_warn = b_warn + k_warn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jadwal WHERE minggu=%s", (minggu,))
            for r in all_rows:
                cur.execute(
                    "INSERT INTO jadwal (minggu, tanggal, hari, sesi, bagian, karyawan_id) VALUES (%s,%s,%s,%s,%s,%s)",
                    (minggu, r["tanggal"], r["hari"], r["sesi"], r["bagian"], r["karyawan_id"])
                )

    # Simpan rekap otomatis
    _simpan_rekap_dari_rows(minggu_str, all_rows, rentang)

    assigned_b = {}
    assigned_k = {}
    for r in b_rows:
        assigned_b[r["nama"]] = assigned_b.get(r["nama"], 0) + 1
    for r in k_rows:
        assigned_k[r["nama"]] = assigned_k.get(r["nama"], 0) + 1

    return {
        "rows": all_rows, "warnings": all_warn,
        "assigned_barista": assigned_b, "assigned_kitchen": assigned_k,
        "rentang": rentang, "minggu": minggu_str,
    }


def get_jadwal_by_minggu(minggu_str: str) -> dict:
    minggu  = date.fromisoformat(minggu_str)
    rentang = format_rentang(minggu)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT j.hari, j.sesi, j.bagian, j.tanggal, k.nama AS karyawan
                FROM jadwal j JOIN karyawan k ON j.karyawan_id=k.id
                WHERE j.minggu=%s
                ORDER BY
                    ARRAY_POSITION(ARRAY['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']::VARCHAR[], j.hari),
                    CASE j.sesi WHEN 'Pagi' THEN 1 ELSE 2 END, j.bagian
            """, (minggu,))
            rows = [dict(r) for r in cur.fetchall()]

    tabel = {h: {"Pagi": {"barista":[],"kitchen":[]}, "Sore": {"barista":[],"kitchen":[]}} for h in HARI_ORDER}
    tanggal_per_hari = {}
    for r in rows:
        tabel[r["hari"]][r["sesi"]][r["bagian"]].append(r["karyawan"])
        tgl = r["tanggal"]
        tanggal_per_hari[r["hari"]] = tgl.strftime("%d/%m") if hasattr(tgl, "strftime") else str(tgl)[5:10].replace("-", "/")

    return {"tabel": tabel, "tanggal_per_hari": tanggal_per_hari, "rentang": rentang, "total": len(rows)}


# ═══════════════════════════════════════════════════════════
# REKAP — core helper
# ═══════════════════════════════════════════════════════════

def _simpan_rekap_dari_rows(minggu_str: str, rows: list, rentang: str):
    """
    Hitung & simpan rekap_minggu dari list rows jadwal,
    lalu rebuild rekap_bulanan.
    rows berisi: {karyawan_id, nama, hari, sesi, tanggal, bagian}
    """
    minggu = date.fromisoformat(minggu_str)
    bulan  = minggu.month
    tahun  = minggu.year

    per_karyawan = defaultdict(lambda: {"detail": [], "pagi": 0, "sore": 0})
    for r in rows:
        kid = r["karyawan_id"]
        tgl = r["tanggal"]
        tgl_str = tgl.strftime("%d/%m") if hasattr(tgl, "strftime") else str(tgl)[5:10].replace("-", "/")
        per_karyawan[kid]["detail"].append({"hari": r["hari"], "sesi": r["sesi"], "tanggal": tgl_str})
        if r["sesi"] == "Pagi":
            per_karyawan[kid]["pagi"] += 1
        else:
            per_karyawan[kid]["sore"] += 1

    with get_conn() as conn:
        with conn.cursor() as cur:
            for kid, data in per_karyawan.items():
                total = data["pagi"] + data["sore"]
                cur.execute("""
                    INSERT INTO rekap_minggu
                      (karyawan_id, minggu, bulan, tahun, rentang, detail, total_shift, shift_pagi, shift_sore)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (karyawan_id, minggu) DO UPDATE SET
                      detail=EXCLUDED.detail, total_shift=EXCLUDED.total_shift,
                      shift_pagi=EXCLUDED.shift_pagi, shift_sore=EXCLUDED.shift_sore,
                      rentang=EXCLUDED.rentang
                """, (kid, minggu, bulan, tahun, rentang,
                      json.dumps(data["detail"]), total, data["pagi"], data["sore"]))

            # Rebuild rekap_bulanan dari rekap_minggu bulan ini
            cur.execute("""
                SELECT karyawan_id,
                       SUM(total_shift) AS total,
                       SUM(shift_pagi)  AS pagi,
                       SUM(shift_sore)  AS sore
                FROM rekap_minggu
                WHERE bulan=%s AND tahun=%s
                GROUP BY karyawan_id
            """, (bulan, tahun))
            for row in cur.fetchall():
                cur.execute("""
                    INSERT INTO rekap_bulanan (karyawan_id, bulan, tahun, total_shift, shift_pagi, shift_sore)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (karyawan_id, bulan, tahun) DO UPDATE SET
                      total_shift=EXCLUDED.total_shift,
                      shift_pagi=EXCLUDED.shift_pagi,
                      shift_sore=EXCLUDED.shift_sore
                """, (row[0], bulan, tahun, row[1], row[2], row[3]))


def _refresh_rekap_dari_jadwal(minggu_str: str):
    """
    Baca ulang jadwal dari DB untuk minggu ini,
    lalu rebuild rekap_minggu & rekap_bulanan.
    Dipanggil setelah tukar/ganti jadwal.
    """
    minggu  = date.fromisoformat(minggu_str)
    rentang = format_rentang(minggu)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT j.hari, j.sesi, j.bagian, j.tanggal, j.karyawan_id, k.nama
                FROM jadwal j JOIN karyawan k ON j.karyawan_id=k.id
                WHERE j.minggu=%s
            """, (minggu,))
            rows = [dict(r) for r in cur.fetchall()]

    _simpan_rekap_dari_rows(minggu_str, rows, rentang)


# ═══════════════════════════════════════════════════════════
# REKAP — read
# ═══════════════════════════════════════════════════════════

def get_rekap_minggu(bulan: int, tahun: int) -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT rm.minggu, rm.rentang, k.nama, k.bagian,
                       rm.total_shift, rm.shift_pagi, rm.shift_sore, rm.detail
                FROM rekap_minggu rm JOIN karyawan k ON rm.karyawan_id=k.id
                WHERE rm.bulan=%s AND rm.tahun=%s
                ORDER BY rm.minggu, k.bagian, k.nama
            """, (bulan, tahun))
            rows = []
            for r in cur.fetchall():
                d = dict(r)
                d["minggu"] = str(d["minggu"])
                rows.append(d)
            return rows


def get_rekap_bulanan(bulan: int, tahun: int) -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT k.nama, k.bagian, rb.total_shift, rb.shift_pagi, rb.shift_sore
                FROM rekap_bulanan rb JOIN karyawan k ON rb.karyawan_id=k.id
                WHERE rb.bulan=%s AND rb.tahun=%s
                ORDER BY k.bagian, rb.total_shift DESC
            """, (bulan, tahun))
            return [dict(r) for r in cur.fetchall()]


def hapus_rekap_bulan_lalu(dari_tanggal=None):
    today         = dari_tanggal or date.today()
    bulan_target  = today.month - 2
    tahun_target  = today.year
    if bulan_target <= 0:
        bulan_target += 12
        tahun_target -= 1

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rekap_minggu  WHERE bulan=%s AND tahun=%s", (bulan_target, tahun_target))
            dm = cur.rowcount
            cur.execute("DELETE FROM rekap_bulanan WHERE bulan=%s AND tahun=%s", (bulan_target, tahun_target))
            db_ = cur.rowcount

    return {"bulan_dihapus": bulan_target, "tahun_dihapus": tahun_target,
            "rekap_minggu_dihapus": dm, "rekap_bulanan_dihapus": db_}


# ═══════════════════════════════════════════════════════════
# PERGANTIAN JADWAL
# ═══════════════════════════════════════════════════════════

def tukar_jadwal(minggu: str, nama1: str, hari1: str, sesi1: str,
                               nama2: str, hari2: str, sesi2: str) -> dict:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, nama FROM karyawan WHERE LOWER(nama)=LOWER(%s)", (nama1,))
            k1 = cur.fetchone()
            cur.execute("SELECT id, nama FROM karyawan WHERE LOWER(nama)=LOWER(%s)", (nama2,))
            k2 = cur.fetchone()
            if not k1: raise ValueError(f"Karyawan '{nama1}' tidak ditemukan.")
            if not k2: raise ValueError(f"Karyawan '{nama2}' tidak ditemukan.")

            cur.execute("SELECT id FROM jadwal WHERE minggu=%s AND hari=%s AND sesi=%s AND karyawan_id=%s",
                        (minggu, hari1, sesi1, k1["id"]))
            j1 = cur.fetchone()
            if not j1: raise ValueError(f"{nama1} tidak punya jadwal {hari1} {sesi1} minggu ini.")

            cur.execute("SELECT id FROM jadwal WHERE minggu=%s AND hari=%s AND sesi=%s AND karyawan_id=%s",
                        (minggu, hari2, sesi2, k2["id"]))
            j2 = cur.fetchone()
            if not j2: raise ValueError(f"{nama2} tidak punya jadwal {hari2} {sesi2} minggu ini.")

            cur.execute("UPDATE jadwal SET karyawan_id=%s WHERE id=%s", (k2["id"], j1["id"]))
            cur.execute("UPDATE jadwal SET karyawan_id=%s WHERE id=%s", (k1["id"], j2["id"]))

            cur.execute("""
                INSERT INTO log_perubahan (tipe,minggu,karyawan1_id,hari1,sesi1,karyawan2_id,hari2,sesi2)
                VALUES ('tukar',%s,%s,%s,%s,%s,%s,%s)
            """, (minggu, k1["id"], hari1, sesi1, k2["id"], hari2, sesi2))

    # Refresh rekap setelah perubahan
    _refresh_rekap_dari_jadwal(minggu)

    return {
        "pesan": f"✅ {nama1} ({hari1} {sesi1}) ↔ {nama2} ({hari2} {sesi2}) berhasil ditukar!",
        "nama1": k1["nama"], "hari1": hari1, "sesi1": sesi1,
        "nama2": k2["nama"], "hari2": hari2, "sesi2": sesi2,
    }


def ganti_jadwal(minggu: str, nama_asli: str, hari: str, sesi: str, nama_pengganti: str) -> dict:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, nama FROM karyawan WHERE LOWER(nama)=LOWER(%s)", (nama_asli,))
            ka = cur.fetchone()
            cur.execute("SELECT id, nama FROM karyawan WHERE LOWER(nama)=LOWER(%s)", (nama_pengganti,))
            kp = cur.fetchone()
            if not ka: raise ValueError(f"Karyawan '{nama_asli}' tidak ditemukan.")
            if not kp: raise ValueError(f"Pengganti '{nama_pengganti}' tidak ditemukan.")

            cur.execute("SELECT id FROM jadwal WHERE minggu=%s AND hari=%s AND sesi=%s AND karyawan_id=%s",
                        (minggu, hari, sesi, ka["id"]))
            j = cur.fetchone()
            if not j: raise ValueError(f"{nama_asli} tidak punya jadwal {hari} {sesi} minggu ini.")

            cur.execute("SELECT id FROM jadwal WHERE minggu=%s AND hari=%s AND sesi=%s AND karyawan_id=%s",
                        (minggu, hari, sesi, kp["id"]))
            if cur.fetchone(): raise ValueError(f"{nama_pengganti} sudah ada jadwal di {hari} {sesi}.")

            cur.execute("UPDATE jadwal SET karyawan_id=%s WHERE id=%s", (kp["id"], j["id"]))

            cur.execute("""
                INSERT INTO log_perubahan
                  (tipe,minggu,karyawan1_id,hari1,sesi1,karyawan2_id,hari2,sesi2,catatan)
                VALUES ('ganti',%s,%s,%s,%s,%s,%s,%s,%s)
            """, (minggu, ka["id"], hari, sesi, kp["id"], hari, sesi,
                  f"Digantikan oleh {kp['nama']}"))

    # Refresh rekap setelah perubahan
    _refresh_rekap_dari_jadwal(minggu)

    return {
        "pesan": f"✅ {nama_asli} di {hari} {sesi} berhasil digantikan {nama_pengganti}!",
        "nama_asli": ka["nama"], "nama_pengganti": kp["nama"], "hari": hari, "sesi": sesi,
    }


def get_log_perubahan(minggu: str) -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT lp.id, lp.tipe, lp.hari1, lp.sesi1, lp.hari2, lp.sesi2,
                       lp.catatan, lp.created_at, k1.nama AS nama1, k2.nama AS nama2
                FROM log_perubahan lp
                JOIN karyawan k1 ON lp.karyawan1_id=k1.id
                JOIN karyawan k2 ON lp.karyawan2_id=k2.id
                WHERE lp.minggu=%s
                ORDER BY lp.created_at DESC
            """, (minggu,))
            rows = []
            for r in cur.fetchall():
                d = dict(r)
                d["created_at"] = d["created_at"].strftime("%d %b %H:%M") if d["created_at"] else ""
                rows.append(d)
            return rows


# ═══════════════════════════════════════════════════════════
# RESET SEMUA DATA
# ═══════════════════════════════════════════════════════════

def reset_semua() -> dict:
    """
    Hapus semua data: availability, jadwal, log_perubahan, rekap_minggu, rekap_bulanan.
    Karyawan TIDAK dihapus.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM log_perubahan")
            log_count = cur.rowcount
            cur.execute("DELETE FROM rekap_bulanan")
            rekap_b = cur.rowcount
            cur.execute("DELETE FROM rekap_minggu")
            rekap_m = cur.rowcount
            cur.execute("DELETE FROM jadwal")
            jadwal_count = cur.rowcount
            cur.execute("DELETE FROM availability")
            avail_count = cur.rowcount

    return {
        "availability_dihapus":   avail_count,
        "jadwal_dihapus":         jadwal_count,
        "log_dihapus":            log_count,
        "rekap_minggu_dihapus":   rekap_m,
        "rekap_bulanan_dihapus":  rekap_b,
    }