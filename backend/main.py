"""
main.py — FastAPI Shift Scheduler (Final)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date, timedelta
import db, parser as llm_parser

app = FastAPI(title="Shift Scheduler API", version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HARI_ORDER = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
BULAN_NAMA = ['','Januari','Februari','Maret','April','Mei','Juni',
              'Juli','Agustus','September','Oktober','November','Desember']


def next_monday() -> str:
    today = date.today()
    days  = (7 - today.weekday()) % 7 or 7
    return (today + timedelta(days=days)).isoformat()


def pivot_jadwal(rows: list, tanggal_per_hari: dict, rentang: str, minggu: str) -> dict:
    tabel = {h: {"Pagi": {"barista":[],"kitchen":[]}, "Sore": {"barista":[],"kitchen":[]}} for h in HARI_ORDER}
    for r in rows:
        tabel[r["hari"]][r["sesi"]][r["bagian"]].append(r.get("nama") or r.get("karyawan", ""))
    return {"tabel": tabel, "tanggal_per_hari": tanggal_per_hari, "rentang": rentang, "minggu": minggu}


# ═══════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════

class InputJadwal(BaseModel):
    teks:   str
    nama:   str | None = None
    bagian: str

class GenerateRequest(BaseModel):
    minggu: str | None = None

class ResetRequest(BaseModel):
    nama: str

class TukarRequest(BaseModel):
    minggu: str
    nama1:  str; hari1: str; sesi1: str
    nama2:  str; hari2: str; sesi2: str

class GantiRequest(BaseModel):
    minggu:          str
    nama_asli:       str
    hari:            str
    sesi:            str
    nama_pengganti:  str


# ═══════════════════════════════════════════════════════════
# AVAILABILITY
# ═══════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "ok", "version": "4.0.0"}


@app.post("/availability")
def input_availability(body: InputJadwal):
    if body.bagian not in ("barista", "kitchen"):
        raise HTTPException(422, "Bagian harus 'barista' atau 'kitchen'.")

    try:
        hasil = llm_parser.parse_availability(body.teks)
    except Exception as e:
        raise HTTPException(502, f"LLM error: {e}")

    if body.nama:
        hasil["nama"] = body.nama

    nama  = hasil.get("nama")
    slots = hasil.get("availability", [])

    if not nama:
        raise HTTPException(422, "Nama tidak ditemukan. Isi field nama atau sebut nama di teks.")
    if not slots:
        raise HTTPException(422, "Tidak ada slot jadwal terbaca. Coba: 'senin pagi, rabu sore'")

    karyawan = db.get_or_create_karyawan(nama, body.bagian)
    if not karyawan:
        raise HTTPException(404, f"Karyawan '{nama}' tidak ditemukan.")
    if karyawan["bagian"] != body.bagian:
        raise HTTPException(409, f"{nama} terdaftar sebagai '{karyawan['bagian']}', bukan '{body.bagian}'.")

    inserted = db.upsert_availability(karyawan["id"], slots)
    return {
        "nama": nama, "bagian": karyawan["bagian"],
        "parsed": slots, "inserted": inserted,
        "pesan": f"✅ {inserted} slot disimpan untuk {nama}!" if inserted > 0
                 else "⚠️ Semua slot sudah tersimpan sebelumnya.",
    }


@app.get("/availability")
def lihat_availability():
    summary   = db.get_availability_summary()
    per_orang = db.get_availability_per_karyawan()

    tabel = {h: {s: {"barista":[],"kitchen":[]} for s in ["Pagi","Sore"]} for h in HARI_ORDER}
    for row in summary:
        names = [k["nama"] for k in row["karyawan"]]
        tabel[row["hari"]][row["sesi"]][row["bagian"]] = names

    return {
        "tabel": tabel,
        "barista": [r for r in per_orang if r["bagian"] == "barista"],
        "kitchen": [r for r in per_orang if r["bagian"] == "kitchen"],
        "semua_cukup": all(r["cukup"] for r in per_orang) if per_orang else False,
    }


@app.post("/reset")
def reset_availability(body: ResetRequest):
    karyawan = db.get_or_create_karyawan(body.nama)
    if not karyawan:
        raise HTTPException(404, f"Karyawan '{body.nama}' tidak ditemukan.")
    db.reset_availability_karyawan(karyawan["id"])
    return {"pesan": f"🗑️ Availability {body.nama} berhasil dihapus."}


@app.get("/karyawan")
def lihat_karyawan():
    return {"karyawan": db.get_all_karyawan()}


# ═══════════════════════════════════════════════════════════
# GENERATE JADWAL
# ═══════════════════════════════════════════════════════════

@app.post("/generate")
def generate_jadwal(body: GenerateRequest):
    minggu = body.minggu or next_monday()
    try:
        hasil = db.generate_and_save_jadwal(minggu)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

    rows = hasil["rows"]
    tabel = {h: {s: {"barista":[],"kitchen":[]} for s in ["Pagi","Sore"]} for h in HARI_ORDER}
    tanggal_per_hari = {}
    for r in rows:
        tabel[r["hari"]][r["sesi"]][r["bagian"]].append(r["nama"])
        tgl = r["tanggal"]
        tanggal_per_hari[r["hari"]] = tgl.strftime("%d/%m") if hasattr(tgl, "strftime") else str(tgl)[5:10].replace("-","/")

    return {
        "minggu": minggu, "rentang": hasil["rentang"],
        "tabel": tabel, "tanggal_per_hari": tanggal_per_hari,
        "total": len(rows), "warnings": hasil["warnings"],
        "assigned_barista": hasil["assigned_barista"],
        "assigned_kitchen": hasil["assigned_kitchen"],
        "pesan": f"✅ Jadwal berhasil dibuat untuk {hasil['rentang']}!",
    }


@app.get("/jadwal/{minggu}")
def lihat_jadwal(minggu: str):
    return db.get_jadwal_by_minggu(minggu)


# ═══════════════════════════════════════════════════════════
# PERGANTIAN JADWAL
# ═══════════════════════════════════════════════════════════

@app.post("/tukar")
def tukar_jadwal(body: TukarRequest):
    try:
        hasil = db.tukar_jadwal(body.minggu,
                                body.nama1, body.hari1, body.sesi1,
                                body.nama2, body.hari2, body.sesi2)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

    jadwal = db.get_jadwal_by_minggu(body.minggu)
    return {**hasil, "jadwal": jadwal}


@app.post("/ganti")
def ganti_jadwal(body: GantiRequest):
    try:
        hasil = db.ganti_jadwal(body.minggu, body.nama_asli,
                                body.hari, body.sesi, body.nama_pengganti)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

    jadwal = db.get_jadwal_by_minggu(body.minggu)
    return {**hasil, "jadwal": jadwal}


@app.get("/log/{minggu}")
def get_log(minggu: str):
    try:
        logs = db.get_log_perubahan(minggu)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"logs": logs}


# ═══════════════════════════════════════════════════════════
# REKAP
# ═══════════════════════════════════════════════════════════

@app.get("/rekap/minggu/{tahun}/{bulan}")
def rekap_minggu(tahun: int, bulan: int):
    try:
        rows = db.get_rekap_minggu(bulan, tahun)
    except Exception as e:
        raise HTTPException(500, str(e))

    from collections import defaultdict
    per_minggu = defaultdict(lambda: {"rentang": "", "barista": [], "kitchen": []})
    for r in rows:
        per_minggu[r["minggu"]]["rentang"] = r["rentang"]
        per_minggu[r["minggu"]][r["bagian"]].append({
            "nama": r["nama"],
            "total_shift": r["total_shift"],
            "shift_pagi": r["shift_pagi"],
            "shift_sore": r["shift_sore"],
            "detail": r["detail"],
        })

    return {
        "bulan": bulan, "tahun": tahun,
        "minggu": [{"minggu": k, **v} for k, v in sorted(per_minggu.items())]
    }


@app.get("/rekap/bulanan/{tahun}/{bulan}")
def rekap_bulanan(tahun: int, bulan: int):
    try:
        rows = db.get_rekap_bulanan(bulan, tahun)
    except Exception as e:
        raise HTTPException(500, str(e))

    return {
        "bulan": bulan, "tahun": tahun,
        "label": f"{BULAN_NAMA[bulan]} {tahun}",
        "barista": [r for r in rows if r["bagian"] == "barista"],
        "kitchen": [r for r in rows if r["bagian"] == "kitchen"],
    }




# ── Hapus Availability (Admin) ───────────────────────────

class HapusSemuaRequest(BaseModel):
    nama: str

class HapusSlotRequest(BaseModel):
    nama: str
    hari: str
    sesi: str

class LihatAvailRequest(BaseModel):
    nama: str


@app.post("/availability/hapus-semua")
def hapus_semua_availability(body: HapusSemuaRequest):
    """Hapus SEMUA availability 1 karyawan (admin only)."""
    karyawan = db.get_or_create_karyawan(body.nama)
    if not karyawan:
        raise HTTPException(404, f"Karyawan '{body.nama}' tidak ditemukan.")
    db.reset_availability_karyawan(karyawan["id"])
    return {"pesan": f"🗑️ Semua availability {body.nama} berhasil dihapus."}


@app.post("/availability/hapus-slot")
def hapus_slot_availability(body: HapusSlotRequest):
    """Hapus 1 slot availability tertentu (admin only)."""
    karyawan = db.get_or_create_karyawan(body.nama)
    if not karyawan:
        raise HTTPException(404, f"Karyawan '{body.nama}' tidak ditemukan.")
    berhasil = db.hapus_slot_availability(karyawan["id"], body.hari, body.sesi)
    if not berhasil:
        raise HTTPException(404, f"Slot {body.hari} {body.sesi} tidak ditemukan untuk {body.nama}.")
    return {"pesan": f"✅ Slot {body.hari} {body.sesi} milik {body.nama} berhasil dihapus."}


@app.post("/availability/lihat")
def lihat_availability_karyawan(body: LihatAvailRequest):
    """Lihat semua slot availability 1 karyawan."""
    karyawan = db.get_or_create_karyawan(body.nama)
    if not karyawan:
        raise HTTPException(404, f"Karyawan '{body.nama}' tidak ditemukan.")
    slots = db.get_availability_karyawan(karyawan["id"])
    return {"nama": body.nama, "slots": slots, "total": len(slots)}



# ── Reset Semua Data (Admin) ─────────────────────────────

class ResetSemuaRequest(BaseModel):
    pass  # body kosong, tidak perlu isi apapun

@app.post("/reset-semua")
def reset_semua(body: ResetSemuaRequest = None):
    """Hapus semua availability, jadwal, log perubahan, dan rekap. Karyawan tetap ada."""
    try:
        hasil = db.reset_semua()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {
        "pesan": "✅ Semua data berhasil direset! Karyawan tetap terdaftar.",
        **hasil
    }

# ═══════════════════════════════════════════════════════════
# CRON — Auto Delete Rekap
# ═══════════════════════════════════════════════════════════

@app.post("/cron/hapus-rekap")
def cron_hapus_rekap():
    """
    Dipanggil Render Cron Job setiap tanggal 10 jam 00:00.
    Schedule di Render: 0 0 10 * *
    Hapus rekap 2 bulan yang lalu (bukan bulan lalu, tapi 2 bulan lalu).
    Contoh: dipanggil 10 April → hapus rekap Februari.
    """
    today = date.today()
    if today.day != 10:
        return {"status": "skip", "pesan": f"Bukan tanggal 10 (hari ini: {today})"}

    try:
        hasil = db.hapus_rekap_bulan_lalu()
    except Exception as e:
        raise HTTPException(500, str(e))

    return {
        "status": "ok",
        "pesan": f"✅ Rekap {hasil['bulan_dihapus']}/{hasil['tahun_dihapus']} dihapus.",
        **hasil
    }