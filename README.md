# 🗓️ Shift Scheduler — AI-Powered Staff Management

An automated shift scheduling system for small businesses (UMKM), built with **FastAPI**, **PostgreSQL**, and **Groq LLM (Llama 3)**. Employees submit their availability in natural language, and the AI parses it automatically into structured data — no forms, no spreadsheets.

---

## 📸 Screenshots

<img width="1920" height="1080" alt="Screenshot (106)" src="https://github.com/user-attachments/assets/330e1a6a-c0dd-488e-bb0b-0c3340ce33ee" />

more: https://drive.google.com/drive/folders/1u3E3dZz0RUZazK8P3q1QyuKizor2RiaV

| Tab | Description |
|-----|-------------|
| `01 / Input Jadwal` | Employee submits availability via free text |
| `02 / Availability` | Admin views all availability + manage data |
| `03 / Generate` | Admin generates weekly schedule |
| `04 / Pergantian` | Anyone can request shift swap or replacement |
| `05 / Rekap` | Admin views monthly shift recap per employee |

---

## ✨ Features

### 👥 For Employees
- Submit weekly availability in **free-form text** (e.g. *"senin-rabu pagi, kamis-minggu sore"*)
- AI automatically parses day ranges, session types, and handles ambiguous input
- Supports Enter-separated or comma-separated format

### ⚙️ For Admin (password protected)
- **Availability Management** — view, delete individual slots, or clear all availability per employee
- **Auto-generate Schedule** — fair rotation algorithm ensures balanced shift distribution
  - Barista (3 people): 2 get 5 shifts, 1 gets 4 — rotates weekly
  - Kitchen (5 people): 3 get 6 shifts, 2 get 5 — rotates weekly
- **Shift Swap** — employees can swap shifts with each other
- **Shift Replacement** — replace an employee's slot with someone else
- **Change Log** — all swaps and replacements are recorded with timestamps
- **Monthly Recap** — total shifts per employee broken down by morning/afternoon
- **Auto-delete** — old recap data is automatically purged via cron job
- **Reset All** — wipe all data (availability, schedules, logs, recaps) while keeping employee records

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| AI / NLP | **Groq API** (Llama 3) | Natural language parsing |
| Database | **PostgreSQL** (Supabase) | Data storage |
| Backend | **FastAPI** (Python) | REST API server |
| Frontend | **HTML + Vanilla JS** | Web interface |

---

## 📁 Project Structure & File Roles

```
shift-scheduler/
├── backend/
│   ├── main.py           # FastAPI application — defines all API endpoints
│   ├── db.py             # Database layer — all PostgreSQL operations,
│   │                     # schedule generation logic, and rotation algorithm
│   ├── parser.py         # AI parser — sends free-text to Groq LLM,
│   │                     # expands day ranges, normalizes sessions
│   ├── requirements.txt  # Python dependencies
│   └── .env              # Environment variables (not committed to Git)
├── frontend/
│   └── index.html        # Single-page web app — all 5 tabs, admin login,
│                         # API calls to backend, responsive UI
└── schema.sql            # PostgreSQL schema — creates all tables and indexes
```

### Detailed File Roles

**`main.py`** — The entry point of the backend. Defines every HTTP endpoint (`/availability`, `/generate`, `/tukar`, `/ganti`, `/rekap`, etc.) and connects requests from the frontend to the database layer.

**`db.py`** — The brain of the system. Contains all database read/write operations and the core scheduling algorithm:
- Validates that each employee submitted at least 6 different days
- Generates fair schedules using a rotation system (who got more shifts last week gets fewer this week)
- Handles shift swaps, replacements, and recap rebuilding after any change

**`parser.py`** — Handles natural language input. Sends the employee's text to Groq's Llama 3 model, then uses Python to expand day ranges (e.g. `"senin-rabu"` → Monday, Tuesday, Wednesday), fill in missing session info, and deduplicate slots.

**`index.html`** — The entire frontend in one file. Contains all 5 tabs, admin login modal, JavaScript for API calls, and CSS styling. No framework — just vanilla HTML/CSS/JS.

**`schema.sql`** — Run once in Supabase to create all tables: `karyawan`, `availability`, `jadwal`, `log_perubahan`, `rekap_minggu`, `rekap_bulanan`.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL (or a free [Supabase](https://supabase.com) account)
- [Groq API key](https://console.groq.com) (free)

### 1. Clone the repository
```bash
git clone https://github.com/your-username/shift-scheduler.git
cd shift-scheduler
```

### 2. Set up the database
1. Create a new project on [Supabase](https://supabase.com)
2. Open the **SQL Editor** and run the contents of `schema.sql`
3. Copy the **Transaction pooler** connection string from **Connect → URI**

### 3. Configure environment variables
Create a `.env` file inside the `backend/` folder:
```env
DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

### 4. Install dependencies & run the backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
Backend running at: `http://localhost:8000`
API docs (Swagger UI): `http://localhost:8000/docs`

### 5. Run the frontend
```bash
cd frontend
python -m http.server 3000
```
Open browser → `http://localhost:3000`

---

## 🗄️ Database Schema

```
karyawan        → employee records (name, role: barista/kitchen)
availability    → submitted availability slots per employee
jadwal          → generated weekly schedules
log_perubahan   → history of all shift swaps and replacements
rekap_minggu    → weekly shift recap per employee
rekap_bulanan   → monthly shift summary per employee
```

---

## 🔐 Admin Access

The admin tabs (Availability, Generate, Rekap) are password-protected on the frontend.

Default password: `admin123`

To change it, edit this line in `index.html`:
```javascript
const ADMIN_PASSWORD = "admin123";
```

---

## 📌 Notes

- Employee data (names & roles) must be added manually via Supabase Table Editor or through a future admin UI
- The AI parser uses Groq's free tier — sufficient for small teams
- Recap data older than 2 months is automatically deleted via the `/cron/hapus-rekap` endpoint (set up as a cron job on your hosting platform)
