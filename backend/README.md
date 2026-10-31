# Ajun (Antar Jemput Universitas) - Backend

Platform pencocokan tumpangan sesama mahasiswa (*peer-to-peer ride matching*) dengan closed-loop immutable ledger.

## Spesifikasi Fase 1a: Fondasi Monorepo, Database Ringan, Google Login & Token Family

### Fitur yang Diimplementasikan
1. **Google OAuth ID Token Verification:**
   - Validasi struktur JWT, `iss` (`accounts.google.com`), dan klaim `sub`.
   - **Klaim Wajib:** `email_verified == true`. Jika `false`, token ditolak keras.
2. **Kunci Identitas Akun:**
   - Pencarian akun saat login dilakukan melalui `google_sub` (stabil dan unik).
   - Email pengguna diperbarui dari token pada tiap login.
3. **Verifikasi Kampus Atomik (Jalur A):**
   - Whitelist domain institusi dengan aturan *dot-boundary* (`domain == allowed || domain.endswith("." + allowed)`).
   - Nilai `is_identity_verified = true` dan `campus_verified_at = NOW()` diupdate **bersamaan dalam satu transaksi database atomik**.
4. **Keamanan Token & Rotasi Refresh Token:**
   - Access token JWT masa berlaku 15 menit.
   - Refresh token kriptografis berformat opaque, disimpan sebagai hash SHA-256.
   - **Token Family Reuse Detection:** Jika token yang telah terpakai (`used_at != NULL`) disajikan kembali, backend otomatis mencabut seluruh token dalam `family_id` yang sama untuk menggagalkan replay attack.
5. **Rate Limiting:**
   - Pembatasan laju pemanggilan pada endpoint otentikasi per client IP (30 request/menit).
6. **Otorisasi Administrator:**
   - Guard `is_admin_email()` membaca variabel lingkungan `ADMIN_EMAILS`.
7. **Pemeriksaan Invarian Konfigurasi Sistem:**
   - Saat inisialisasi, memvalidasi aturan $\text{REOPEN\_MIN\_LEAD\_MINUTES} \ge \text{MIN\_CONFIRMATION\_LEAD\_MINUTES}$.

---

## Petunjuk Menjalankan Backend Secara Lokal (Laptop 8 GB RAM Friendly)

### 1. Prasyarat
- Python 3.11+
- Tidak memerlukan Docker Desktop berat. Secara default menggunakan SQLite async (`sqlite+aiosqlite:///./ajun.db`) yang sangat ringan, atau koneksi cloud free-tier PostgreSQL (Neon.tech / Supabase).

### 2. Instalasi Dependensi
```bash
cd backend
pip install -r requirements.txt
```

### 3. Konfigurasi Lingkungan
Salin file konfigurasi:
```bash
cp .env.example .env
```
Sesuaikan variabel di `.env`:
- `DATABASE_URL`: `sqlite+aiosqlite:///./ajun.db` (atau URL PostgreSQL Anda)
- `ADMIN_EMAILS`: Email admin Anda
- `JWT_SECRET`: Kunci rahasia JWT
- `TOMBSTONE_HMAC_SECRET`: Kunci rahasia HMAC untuk tombstone

### 4. Menjalankan Server Backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Akses dokumentasi interaktif API di browser:
- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 5. Menjalankan Rangkaian Tes Otomatis (Pytest)
```bash
python3 -m pytest tests/ -v
```
Seluruh 19 pengujian Fase 1a akan dieksekusi dalam tempo < 1 detik.
