-- ============================================================
-- SHIFT SCHEDULER — schema.sql
-- Jalankan sekali di Supabase SQL Editor
-- ============================================================

-- Urutan DROP penting (FK dulu)
DROP TABLE IF EXISTS log_perubahan  CASCADE;
DROP TABLE IF EXISTS rekap_bulanan  CASCADE;
DROP TABLE IF EXISTS rekap_minggu   CASCADE;
DROP TABLE IF EXISTS jadwal         CASCADE;
DROP TABLE IF EXISTS availability   CASCADE;
DROP TABLE IF EXISTS karyawan       CASCADE;

-- ── Karyawan ─────────────────────────────────────────────
CREATE TABLE karyawan (
  id     SERIAL PRIMARY KEY,
  nama   VARCHAR(50) NOT NULL UNIQUE,
  bagian VARCHAR(10) NOT NULL CHECK (bagian IN ('barista','kitchen'))
);

-- ── Availability ─────────────────────────────────────────
CREATE TABLE availability (
  id          SERIAL PRIMARY KEY,
  karyawan_id INT        NOT NULL REFERENCES karyawan(id) ON DELETE CASCADE,
  hari        VARCHAR(10) NOT NULL CHECK (hari IN ('Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu')),
  sesi        VARCHAR(10) NOT NULL CHECK (sesi IN ('Pagi','Sore')),
  UNIQUE (karyawan_id, hari, sesi)
);

-- ── Jadwal ───────────────────────────────────────────────
CREATE TABLE jadwal (
  id          SERIAL PRIMARY KEY,
  minggu      DATE        NOT NULL,  -- tanggal Senin minggu tsb
  tanggal     DATE        NOT NULL,  -- tanggal spesifik hari tsb
  hari        VARCHAR(10) NOT NULL,
  sesi        VARCHAR(10) NOT NULL,
  bagian      VARCHAR(10) NOT NULL CHECK (bagian IN ('barista','kitchen')),
  karyawan_id INT         NOT NULL REFERENCES karyawan(id) ON DELETE CASCADE
);

CREATE INDEX idx_jadwal_minggu   ON jadwal(minggu);
CREATE INDEX idx_jadwal_karyawan ON jadwal(karyawan_id);

-- ── Log Perubahan ────────────────────────────────────────
CREATE TABLE log_perubahan (
  id           SERIAL PRIMARY KEY,
  tipe         VARCHAR(10)  NOT NULL CHECK (tipe IN ('tukar','ganti')),
  minggu       DATE         NOT NULL,
  karyawan1_id INT          NOT NULL REFERENCES karyawan(id),
  hari1        VARCHAR(10)  NOT NULL,
  sesi1        VARCHAR(10)  NOT NULL,
  karyawan2_id INT          NOT NULL REFERENCES karyawan(id),
  hari2        VARCHAR(10),           -- null untuk ganti
  sesi2        VARCHAR(10),           -- null untuk ganti
  catatan      TEXT,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_log_minggu ON log_perubahan(minggu);

-- ── Rekap Mingguan ───────────────────────────────────────
CREATE TABLE rekap_minggu (
  id          SERIAL PRIMARY KEY,
  karyawan_id INT         NOT NULL REFERENCES karyawan(id) ON DELETE CASCADE,
  minggu      DATE        NOT NULL,
  bulan       INT         NOT NULL,
  tahun       INT         NOT NULL,
  rentang     VARCHAR(40) NOT NULL,
  detail      JSONB       NOT NULL DEFAULT '[]',   -- [{hari, sesi, tanggal}]
  total_shift INT         NOT NULL DEFAULT 0,
  shift_pagi  INT         NOT NULL DEFAULT 0,
  shift_sore  INT         NOT NULL DEFAULT 0,
  UNIQUE (karyawan_id, minggu)
);

CREATE INDEX idx_rekap_minggu_bulan ON rekap_minggu(bulan, tahun);

-- ── Rekap Bulanan ────────────────────────────────────────
CREATE TABLE rekap_bulanan (
  id          SERIAL PRIMARY KEY,
  karyawan_id INT  NOT NULL REFERENCES karyawan(id) ON DELETE CASCADE,
  bulan       INT  NOT NULL,
  tahun       INT  NOT NULL,
  total_shift INT  NOT NULL DEFAULT 0,
  shift_pagi  INT  NOT NULL DEFAULT 0,
  shift_sore  INT  NOT NULL DEFAULT 0,
  UNIQUE (karyawan_id, bulan, tahun)
);

CREATE INDEX idx_rekap_bulanan_bulan ON rekap_bulanan(bulan, tahun);

-- ============================================================
-- DATA KARYAWAN
-- ============================================================
INSERT INTO karyawan (nama, bagian) VALUES
  ('Frans',  'barista'), ('Dito',  'barista'), ('Gea', 'barista'),
  ('Eko',   'kitchen'), ('Fajar', 'kitchen'), ('Sila',  'kitchen'),
  ('Ivan',  'kitchen'), ('Julia', 'kitchen')