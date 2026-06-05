"""
parser.py — Parse teks bebas availability
Strategi: AI hanya ekstrak token mentah (segment), Python yang expand range & fill sesi
"""

import os, json, re, requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"

VALID_HARI = {"Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"}
VALID_SESI = {"Pagi","Sore"}
HARI_ORDER = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]

HARI_MAP = {
    "senin":"Senin","sn":"Senin","sen":"Senin",
    "selasa":"Selasa","sl":"Selasa","sel":"Selasa",
    "rabu":"Rabu","rb":"Rabu","rab":"Rabu",
    "kamis":"Kamis","km":"Kamis","kam":"Kamis","kms":"Kamis",
    "jumat":"Jumat","jm":"Jumat","jum":"Jumat","jmt":"Jumat",
    "sabtu":"Sabtu","sb":"Sabtu","sab":"Sabtu",
    "minggu":"Minggu","mg":"Minggu","min":"Minggu","mgg":"Minggu",
}

SYSTEM_PROMPT = """
Kamu adalah parser jadwal shift kerja bahasa Indonesia.

Tugasmu: ekstrak segment jadwal dari teks. Setiap segment = 1 kelompok hari + sesi.

Format output:
{"nama": null, "segments": [
  {"hari": "Senin", "sampai": null, "sesi": "Pagi"},
  {"hari": "Kamis", "sampai": "Minggu", "sesi": "Pagi/Sore"}
]}

Aturan field:
- hari   : hari pertama atau satu-satunya
- sampai : hari terakhir jika range (X-Y), null jika bukan range
- sesi   : "Pagi" / "Sore" / "Pagi/Sore" / null jika tidak disebut
  pagi/subuh/morning    → "Pagi"
  sore/malam/malem      → "Sore"
  pagi/sore / pagi&sore → "Pagi/Sore"

CONTOH:
Input : "senin-rabu pagi/sore, kamis-minggu pagi"
Output: {"nama": null, "segments": [
  {"hari": "Senin", "sampai": "Rabu",   "sesi": "Pagi/Sore"},
  {"hari": "Kamis", "sampai": "Minggu", "sesi": "Pagi"}
]}

Input : "senin, rabu pagi, selasa, kamis-sabtu sore"
Output: {"nama": null, "segments": [
  {"hari": "Senin",  "sampai": null,    "sesi": null},
  {"hari": "Rabu",   "sampai": null,    "sesi": "Pagi"},
  {"hari": "Selasa", "sampai": null,    "sesi": "Sore"},
  {"hari": "Kamis",  "sampai": "Sabtu", "sesi": "Sore"}
]}

Balas HANYA JSON tanpa teks lain.
""".strip()


def normalize_hari(h: str) -> str | None:
    if not h:
        return None
    return HARI_MAP.get(h.lower().strip())


def expand_range(hari1: str, hari2: str) -> list:
    try:
        i1 = HARI_ORDER.index(hari1)
        i2 = HARI_ORDER.index(hari2)
        return HARI_ORDER[i1:i2+1] if i1 <= i2 else [hari1]
    except ValueError:
        return [hari1]


def segments_to_slots(segments: list) -> list:
    """Konversi segments → slot individual, handle range & fill sesi null."""

    # Step 1: expand
    expanded = []
    for seg in segments:
        hari1 = normalize_hari(str(seg.get("hari", "")))
        if not hari1:
            continue

        hari2 = normalize_hari(str(seg.get("sampai", "") or ""))
        sesi  = seg.get("sesi") or None

        hari_list = expand_range(hari1, hari2) if hari2 else [hari1]

        if sesi and "/" in str(sesi):
            sesi_list = ["Pagi", "Sore"]
        elif sesi and str(sesi).capitalize() in VALID_SESI:
            sesi_list = [str(sesi).capitalize()]
        else:
            sesi_list = [None]

        for hari in hari_list:
            for s in sesi_list:
                expanded.append({"hari": hari, "sesi": s})

    # Step 2: fill sesi null → ikut terdekat ke kanan, lalu kiri
    n = len(expanded)
    for i in range(n):
        if expanded[i]["sesi"] is not None:
            continue
        found = None
        for j in range(i+1, n):
            if expanded[j]["sesi"] is not None:
                found = expanded[j]["sesi"]
                break
        if found is None:
            for j in range(i-1, -1, -1):
                if expanded[j]["sesi"] is not None:
                    found = expanded[j]["sesi"]
                    break
        expanded[i]["sesi"] = found or "Pagi"

    # Step 3: filter valid + deduplicate
    seen, result = set(), []
    for s in expanded:
        if s["hari"] in VALID_HARI and s["sesi"] in VALID_SESI:
            key = (s["hari"], s["sesi"])
            if key not in seen:
                seen.add(key)
                result.append({"hari": s["hari"], "sesi": s["sesi"]})

    return result


def parse_availability(teks: str) -> dict:
    teks_normalized = teks.replace('\n', ', ').replace('\r', '')

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": teks_normalized},
        ],
        "temperature": 0,
        "max_tokens": 600,
    }

    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()

    raw = re.sub(r"```json|```", "", resp.json()["choices"][0]["message"]["content"]).strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except Exception:
                return {"nama": None, "availability": [], "error": f"Gagal parse: {raw}"}
        else:
            return {"nama": None, "availability": [], "error": f"Gagal parse: {raw}"}

    segments     = result.get("segments", [])
    availability = segments_to_slots(segments)

    return {"nama": result.get("nama"), "availability": availability}