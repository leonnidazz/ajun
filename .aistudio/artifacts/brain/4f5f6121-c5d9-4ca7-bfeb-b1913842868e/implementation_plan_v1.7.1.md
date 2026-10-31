# Ajun (Antar Jemput Universitas) - Implementation Plan (Revisi v1.7.1 - Final Standalone)

Dokumen spesifikasi teknis dan rencana implementasi menyeluruh untuk aplikasi **Ajun (Antar Jemput Universitas)**. Dirancang untuk pencocokan tumpangan sesama mahasiswa (*peer-to-peer ride matching*) dengan rute dan jadwal bersama, verifikasi titik jemput, sistem akuntansi dompet tertutup (*closed-loop immutable ledger*) dengan *hold/release/settle* atomik, row-level locking anti-deadlock, dan arsitektur backend hemat sumber daya (*RAM 8 GB friendly*).

---

## User Review & Critical Decisions (Status Keputusan & Catatan Isu Terbuka)

> [!NOTE]
> **Isu yang telah tuntas diselesaikan pada revisi v1.7.1:**
> 1. **Kolom `matched_at` pada `ride_matches`:** Ditambahkan sebagai `TIMESTAMPTZ NULL` (diset saat transisi ke `MATCHED`) sebagai basis kalkulasi `confirmation_deadline`.
> 2. **Jaminan Waktu Konfirmasi Minimal 15 Menit:** Formula dinamis memastikan jendela konfirmasi tidak terpotong oleh waktu keberangkatan yang terlalu dekat.
> 3. **Batas Waktu Berbasis Konfigurasi (`system_configurations`):** Seluruh durasi waktu (`REQUEST_RESPONSE_MINUTES`, `CONFIRMATION_WINDOW_MINUTES`, `REOPEN_MIN_LEAD_MINUTES`, `MIN_CONFIRMATION_LEAD_MINUTES`, `MIN_REQUEST_LEAD_MINUTES`) dibaca dinamis dari database, bukan di-hardcode.
> 4. **Penegasan Indeks `uq_request_pair`:** Indeks parsial unik hanya mencakup `('REQUESTED', 'REJECTED')`, sehingga pasangan yang kedaluwarsa (`EXPIRED`) dapat diajukan kembali selama waktu mencukupi.
> 5. **Atomisitas Verifikasi Identitas Kampus:** Kolom `is_identity_verified = true` dan `campus_verified_at = NOW()` selalu dieksekusi bersamaan dalam satu transaksi database atomik.

> [!IMPORTANT]
> **Daftar Isu Terbuka & Keputusan yang Dijadwalkan pada Fase Terkait:**
> 1. **Validasi Invarian Lead Time (Fase 3):** `REOPEN_MIN_LEAD_MINUTES` digunakan bersama untuk pembukaan kembali ride dan buffer `expires_at`. Jaminan konfirmasi minimal 15 menit hanya berlaku jika $\text{REOPEN\_MIN\_LEAD\_MINUTES} \ge \text{MIN\_CONFIRMATION\_LEAD\_MINUTES}$. Hal ini divalidasi ketat saat startup/pemuatan `system_configurations` (reject/clamp nilai invalid) dan ditambahkan ke rangkaian tes otomatis Fase 3.
> 2. **Penyelesaian Detail Pembayaran (Fase 8):** Rincian desain transisi keluar `PARTIALLY_REFUNDED`, formula float dengan refund parsial, dan mekanisme refund paket yang terpakai sebagian dicatat pada Bagian 7 dan akan difinalisasi saat memasuki Fase 8.
> 3. **Gerbang Produksi Hukum (Sebelum `PAYMENT_ENV=production`):** Pertanyaan kepatuhan hukum UU PDP, uang elektronik BI, regulasi app store, dan KYB gateway pada Bagian 8 wajib dijawab tuntas sebelum fitur pembayaran diaktifkan di production.

---

## Ringkasan Perubahan (v1.7 $\rightarrow$ v1.7.1)

1. **Google Sub sebagai Kunci Login Pengguna:** Penambahan kolom `google_sub VARCHAR UNIQUE NULL` pada `users` (dikosongkan saat wipe PII) dan tipe `GOOGLE_SUB` pada `tombstone_identifiers` untuk lookup login yang stabil; `email` direfresh pada tiap login dari verified token dan bukan sebagai identity key.
2. **Pelacakan Verifikasi Kampus & Tabel `campus_verification_codes`:** Penambahan kolom `campus_verified_at` dan `campus_verification_method` pada `users`, serta tabel `campus_verification_codes` di Fase 1b dengan batas resend dan 5 kali percobaan (penyedia email Jalur B divalidasi di Fase 1b; dibangun hanya jika Jalur A tidak dapat digunakan). Pengecekan status `is_identity_verified = true` dan `campus_verified_at = NOW()` selalu dieksekusi bersamaan dalam satu transaksi database atomik.
3. **Pemberian Sanksi Tanpa Blokir Registrasi pada Tombstone:** Kecocokan identifier tombstone tidak memblokir pendaftaran akun baru, namun menggugurkan bonus 30 koin dan memulihkan sanksi aktif serta strike 90 hari terakhir.
4. **Variabel Lingkungan `SERVICE_FEE_COINS` & `CRON_SECRET`:** Penegasan `SERVICE_FEE_COINS` (default 1; bernilai 0 pada pilot-lite tanpa penulisan baris hold/fee dan tanpa cek saldo) dan `CRON_SECRET` murni sebagai environment variable di Aturan Mutlak.
5. **Penyempurnaan Alur `REQUESTED` & Indeks Unik Anti-Re-request:** Transisi `REQUESTED` $\rightarrow$ `EXPIRED`/`REJECTED` tidak mengubah status ride (tetap `OPEN`). Partial unique index `uq_request_pair` mencakup status `('REQUESTED', 'REJECTED')` sehingga tawaran yang ditolak tidak dapat diajukan kembali, namun tawaran yang kedaluwarsa (`EXPIRED`) tetap dapat diajukan ulang jika waktu memungkinkan.
6. **Formulasi Batas Waktu Dinamis (*Timeouts*):** Penambahan kolom `matched_at TIMESTAMPTZ NULL` pada `ride_matches`. Penentuan batas waktu membaca konfigurasi dari `system_configurations`:
   - `expires_at = LEAST(created_at + REQUEST_RESPONSE_MINUTES, departure_time - REOPEN_MIN_LEAD_MINUTES)`
   - `confirmation_deadline = LEAST(matched_at + CONFIRMATION_WINDOW_MINUTES, departure_time - MIN_CONFIRMATION_LEAD_MINUTES)`
   - Permintaan baru wajib ditolak jika sisa waktu menuju keberangkatan $< \text{MIN\_REQUEST\_LEAD\_MINUTES}$ (default 45 menit).
   - Validasi konfigurasi sistem memastikan mutlak bahwa `REOPEN_MIN_LEAD_MINUTES >= MIN_CONFIRMATION_LEAD_MINUTES` demi menjaga garansi waktu konfirmasi 15 menit.
7. **Transisi Pembatalan Ride Mandiri `OPEN` $\rightarrow$ `CANCELLED`:** Pemilik dapat membatalkan ride yang belum match (`cancel_reason = 'RIDE_CANCELLED'` pada tawaran terkait), dan perubahan rute/jadwal diblokir jika terdapat match non-terminal.
8. **Integritas `estimated_arrival_at` & Fallback Sweeper:** Kolom `estimated_arrival_at` wajib terisi saat `IN_PROGRESS` (CHECK constraint), dan sweeper auto-complete menggunakan fallback `COALESCE(estimated_arrival_at, departure_time + INTERVAL '3 hours')`.
9. **Koreksi Logika Sweeper Task 2 & Task 5:** Task 2 menegaskan ride pihak yang tidak konfirmasi menjadi `CANCELLED` sementara rekan mengikuti aturan lead time; Task 5 melakukan join ke `no_show_reports` untuk membaca `review_deadline`.
10. **Catatan Desain Fase 8 (Belum Diputuskan):** Dokumentasi pada Bagian 7 mencakup aturan transisi `PARTIALLY_REFUNDED`, formula float untuk paket terpakai sebagian, dan mekanisme refund parsial.

---

## Non-Goals (Batasan Tegas Sistem)

Sesuai aturan kepatuhan fintech dan batas hukum uang elektronik *closed-loop*:
1. **Tidak Ada Transfer Koin Antar Pengguna:** Koin tidak dapat dikirim, dibagikan, atau dipindahkan antar-akun pengguna.
2. **Tidak Ada Penarikan Tunai (*Cashout / Withdrawal*):** Koin tidak dapat dicairkan kembali menjadi uang tunai atau saldo e-wallet/rekening bank.
3. **Tidak Ada Penggunaan di Luar Ajun:** Koin hanya sah untuk pembayaran biaya layanan platform Ajun.
4. **Tidak Ada Pemrosesan Ongkos Perjalanan:** Ajun **tidak** memproses, menagih, atau menampung ongkos tumpangan antara Driver dan Passenger. Ongkos adalah kesepakatan langsung di luar sistem.

---

## 1. Overview & Model Ekonomi Koin

- **Definisi Produk:** Platform pencocokan tumpangan (*matching platform*), bukan penyedia jasa transportasi atau penentu tarif.
- **Biaya Layanan:** Dikenakan berbasis koin tertutup (1 koin Driver + 1 koin Passenger per perjalanan sukses). Nilai konseptual 1 koin = Rp500. Dikonfigurasi melalui environment variable `SERVICE_FEE_COINS` (default 1; bernilai 0 pada mode pilot-lite).
- **Bonus Pengguna Baru:** 30 koin bonus gratis, dikreditkan otomatis **hanya setelah verifikasi identitas kampus berhasil** dan dipastikan tidak memiliki catatan di tabel tombstone. Jika identitas yang dinormalisasi cocok dengan tombstone aktif, pendaftaran akun baru tetap diizinkan tetapi bonus 30 koin tidak diberikan, serta sanksi aktif dan strike 90 hari terakhir dipulihkan ke akun baru.
- **Jalur Verifikasi Kampus:**
  - **Jalur A (Primer - 100% Gratis):** Pemeriksaan klaim token Google (`email_verified == true` dan kecocokan domain email institusi dengan aturan *dot-boundary* whitelist).
  - **Jalur B (Sekunder / Cadangan):** Pengiriman kode OTP 6-digit ke email kampus via free tier provider (Resend/Brevo) dengan batas waktu 10 menit dan *rate limiting*. Dibangun hanya jika Jalur A tidak dapat digunakan oleh mahasiswa kampus target.
  - *Catatan:* WhatsApp OTP tetap nonaktif secara default karena menimbulkan biaya per pesan.
  - *Konsistensi Data:* Kolom `is_identity_verified = true` dan `campus_verified_at = NOW()` di tabel `users` **wajib selalu diset bersamaan dalam satu transaksi database atomik**.
- **Koin Tertutup (Closed-Loop Ledger):** Tabel buku besar keuangan bersifat *append-only* (tanpa `UPDATE`/`DELETE`). Semua jumlah uang dan koin dicatat sebagai bilangan bulat (*integer*).

---

## 2. Tabel Transisi Status Lengkap (Single Source of Truth)

Siklus hidup perjalanan dikendalikan oleh `ride_matches.status` sebagai *single source of truth*. Status pada `driver_ride` dan `passenger_ride` bergerak sinkron mengikuti perubahan pada match.

### A. Tabel Transisi `ride_matches` (Master Lifecycle)
| Status Asal | Status Tujuan | Pemicu (Trigger) | Efek ke Ledger | Dampak ke `driver_ride` & `passenger_ride` |
| :--- | :--- | :--- | :--- | :--- |
| *(None)* | `REQUESTED` | Driver mengirim ajakan tumpangan ke Passenger | Tidak ada | Status kedua ride tetap `OPEN` (tersembunyi dari pencarian lain) |
| `REQUESTED` | `EXPIRED` | Batas waktu respons `expires_at` terlewati | Tidak ada | Status kedua ride tidak diubah (tetap `OPEN`; jika departure_time lewat, diubah oleh sweeper) |
| `REQUESTED` | `REJECTED` | Passenger menolak ajakan Driver | Tidak ada | Status kedua ride tidak diubah (tetap `OPEN`) |
| `REQUESTED` | `CANCELLED` *(Superseded)* | Match lain pada ride yang sama diterima (`MATCHED`) | Tidak ada (`cancel_reason = 'SUPERSEDED'`) | Ride mengikuti match yang diterima |
| `REQUESTED` | `MATCHED` | Passenger menerima ajakan (atomic lock & time-overlap check) | Tidak ada | Kedua ride berubah menjadi `MATCHED`. Seluruh match `REQUESTED` lain pada ride ini otomatis `CANCELLED`. Kolom `matched_at = NOW()` diset. |
| `MATCHED` *(parsial)*| `MATCHED` | Salah satu pihak klik konfirmasi (saldo $\ge \text{SERVICE\_FEE\_COINS}$) | Catat `HOLD_SERVICE_FEE` (-1) via `on_party_confirmed()` (dilewati jika fee = 0) | Status ride tetap `MATCHED` |
| `MATCHED` | `CONFIRMED` | Pihak kedua klik konfirmasi (saldo $\ge \text{SERVICE\_FEE\_COINS}$) | Catat `HOLD_SERVICE_FEE` (-1) via `on_party_confirmed()` (dilewati jika fee = 0) | Status kedua ride tetap `MATCHED` (terkunci untuk jalan) |
| `MATCHED` | `CANCELLED` | Salah satu pihak batal sebelum konfirmasi lengkap | `RELEASE_HOLD` (+1) jika ada pihak yang sempat konfirmasi | Ride pembatal $\rightarrow$ `CANCELLED`; ride rekan $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `MATCHED` | `EXPIRED` *(Satu Pihak)* | Deadline konfirmasi lewat & hanya 1 pihak konfirmasi | `RELEASE_HOLD` (+1) pihak yang konfirmasi via `on_expired()` | Pihak tak konfirmasi $\rightarrow$ `CANCELLED`; pihak konfirmasi $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `MATCHED` | `EXPIRED` *(Nol Pihak)* | Deadline konfirmasi lewat & kedua pihak tak konfirmasi | Tidak ada hold | Kedua ride $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `CONFIRMED` | `IN_PROGRESS` | Driver klik *"Mulai Perjalanan"* setelah penumpang naik | Tidak ada | Status kedua ride tetap `MATCHED` (`estimated_arrival_at` wajib terisi) |
| `IN_PROGRESS` | `COMPLETED` | (a) Passenger klik "Perjalanan OK" awal; ATAU (b) 60 mnt pasca Driver klik selesai; ATAU (c) ETA + 2 jam | Settle: `RELEASE_HOLD` (+1) lalu `SERVICE_FEE` (-1) via `on_completed()` (dilewati jika fee = 0) | Status kedua ride menjadi `COMPLETED` |
| `IN_PROGRESS` | `DISPUTED` | Passenger mengajukan sanggahan dalam jendela 60 menit | Koin hold dibekukan | Status kedua ride tetap `MATCHED` |
| `DISPUTED` | `COMPLETED` | Admin memvalidasi perjalanan berhasil | Settle: `RELEASE_HOLD` (+1) lalu `SERVICE_FEE` (-1) | Status kedua ride menjadi `COMPLETED` |
| `DISPUTED` | `CANCELLED` | Admin batalkan ATAU timeout 72 jam tanpa keputusan admin | Eksekusi `RELEASE_HOLD` (+1) kedua belah pihak | Status kedua ride menjadi `CANCELLED` |
| `CONFIRMED` | `NO_SHOW_REPORTED` | Salah satu pihak lapor no-show pasca toleransi 10 mnt | Koin hold dibekukan | Status kedua ride tetap `MATCHED` |
| `NO_SHOW_REPORTED`| `NO_SHOW` | Laporan diverifikasi VALID oleh admin (maks. 72 jam) | Eksekusi `RELEASE_HOLD` (+1) kedua pihak; catat strike ke terlapor | Status kedua ride menjadi `CANCELLED` |
| `NO_SHOW_REPORTED`| `CANCELLED` | Laporan REJECTED oleh admin ATAU timeout 72 jam lewat | Eksekusi `RELEASE_HOLD` (+1) kedua pihak (tanpa sanksi) | Status kedua ride menjadi `CANCELLED` |
| `CONFIRMED` | `CANCELLED` *(Pra-Jalan)* | Pembatalan sah oleh salah satu pihak sebelum berangkat | Eksekusi `RELEASE_HOLD` (+1) kedua pihak; jika telat (<15 mnt), catat late cancel | Ride pembatal $\rightarrow$ `CANCELLED`; ride rekan $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `IN_PROGRESS` | `CANCELLED` *(Di Jalan)* | Pembatalan darurat di jalan (force majeure) | Eksekusi `RELEASE_HOLD` (+1) kedua pihak | Status KEDUA ride menjadi `CANCELLED` |

*Catatan partial unique index:* Indeks `uq_request_pair` hanya membatasi pasangan pada status `('REQUESTED', 'REJECTED')`. Pasangan yang mengalami kedaluwarsa (`EXPIRED`) **dapat diajukan kembali** (*can be re-requested*) selama rute masih valid dan waktu mencukupi.

### B. Tabel Transisi `rides`
| Status Asal | Status Tujuan | Pemicu (Trigger) | Efek ke Ledger | Keterangan |
| :--- | :--- | :--- | :--- | :--- |
| *(None)* | `OPEN` | Pengguna mempublikasikan jadwal/rute | Tidak ada | Muncul di pencarian kandidat |
| `OPEN` | `CANCELLED` | Pemilik membatalkan rute yang belum match | Tidak ada | Tawaran `REQUESTED` terkait otomatis `CANCELLED` (`cancel_reason = 'RIDE_CANCELLED'`). Ditolak jika match aktif sudah terbentuk. |
| `OPEN` | `MATCHED` | Salah satu tawaran diterima (`ride_matches` $\rightarrow$ `MATCHED`) | Tidak ada | Terkunci dalam proses perjalanan |
| `OPEN` | `EXPIRED` | Waktu keberangkatan lewat tanpa pasangan (`departure_time < NOW()`) | Tidak ada | Dijalankan oleh lazy check & sweeper |
| `MATCHED` | `OPEN` | Pasangan membatalkan / expired dan sisa waktu $\ge \text{REOPEN\_MIN\_LEAD\_MINUTES}$ | Tidak ada | Kembali aktif mencari pasangan baru |
| `MATCHED` | `EXPIRED` | Pasangan membatalkan / expired tetapi sisa waktu $< \text{REOPEN\_MIN\_LEAD\_MINUTES}$ | Tidak ada | Waktu terlalu mepet untuk dicocokkan ulang |
| `MATCHED` | `COMPLETED` | Match terkait mencapai status `COMPLETED` | Mengikuti match | Perjalanan tuntas |
| `MATCHED` | `CANCELLED` | Match dibatalkan oleh pengguna ini / kondisi darurat | Mengikuti match | Perjalanan batal |

*Aturan Immutability Rute:* Nilai `departure_time` dan rute koordinat suatu ride dilarang diubah (*immutable*) selama masih ada match non-terminal yang mereferensikannya.

### C. Tabel Transisi `topup_orders`
| Status Asal | Status Tujuan | Pemicu (Trigger) | Efek ke Ledger |
| :--- | :--- | :--- | :--- |
| *(None)* | `PENDING` | Pengguna memilih paket koin & membuat order | Tidak ada |
| `PENDING` | `PAID` | Webhook gateway valid & `paid_amount_idr == amount_idr` | Kreditkan koin: `TOPUP_PAID` (+koin) |
| `PENDING` | `EXPIRED` | Batas waktu bayar habis tanpa notifikasi bayar | Tidak ada |
| `PENDING` | `FAILED` | Webhook gateway menyatakan gagal / dibatalkan | Tidak ada |
| `PENDING` | `REVIEW_REQUIRED` | Webhook valid tapi `paid_amount_idr != amount_idr` | Tidak ada koin ditambah; antrean review admin |
| `REVIEW_REQUIRED`| `PAID` | Admin menyetujui selisih nominal bayar & kredit koin | Kreditkan koin: `TOPUP_PAID` (+koin) |
| `REVIEW_REQUIRED`| `REFUND_REQUIRED` | Admin memutuskan dana dikembalikan via payment gateway | Tidak ada koin ditambah; catat antrean refund |
| `REVIEW_REQUIRED`| `REFUNDED` | Pengembalian dana sukses via payment gateway | Tidak ada koin diubah |
| `EXPIRED` | `PAID` *(Late)* | Webhook valid diterima pasca expired & saldo $\le$ max | Kreditkan koin: `TOPUP_PAID` (+koin) |
| `EXPIRED` | `REFUND_REQUIRED` | Webhook valid diterima pasca expired tapi saldo > max | Tidak ada koin ditambah; tandai refund |
| `REFUND_REQUIRED`| `REFUNDED` | Pengembalian dana sukses via payment gateway | Tidak ada koin diubah |
| `PAID` | `REFUNDED` | Pengembalian dana penuh atas order paid yang belum dipakai | Debet koin: `REFUND` (-koin berbayar utuh) |
| `PAID` | `PARTIALLY_REFUNDED` | Pengembalian dana parsial atas koin berbayar yang tersisa | Debet koin: `REFUND` (-sisa koin berbayar) |

---

## 3. Technical Architecture & Database Strategy

```
┌────────────────────────────────────────────────────────┐
│               FLUTTER CLIENT (MOBILE/WEB)              │
│  - Google Sign-In & Campus Domain Verify (Jalur A/B)   │
│  - OpenStreetMap (flutter_map / latlong2)              │
│  - Dynamic Countdown & Real-time Lazy Status Poll      │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS / REST API (Rate Limited)
┌───────────────────────────▼────────────────────────────┐
│              FASTAPI BACKEND (PYTHON 3.11+)            │
│  ├── Auth & Token Rotation (refresh_tokens Family Check│
│  ├── Admin Auth Guard (is_admin_email via ADMIN_EMAILS)│
│  ├── Lazy Expiration Evaluator (Per-Request Check)     │
│  ├── Ride Lifecycle Engine (Locked Overlap & Supersede)│
│  ├── Matching Engine (Weighted Score 35/25/25/15)      │
│  ├── Safety & No-Show Service (72h Deadline / Evidences│
│  ├── Immutable Ledger Engine (SELECT FOR UPDATE ASC)   │
│  ├── Background Sweeper (11 Tasks: Catch-Up Safe)      │
│  └── Payment Adapter (Sandbox Webhook & Idempotency)   │
└───────────────────────────┬────────────────────────────┘
                            │ Async Connection Pool
┌───────────────────────────▼────────────────────────────┐
│          POSTGRESQL (NEON / SUPABASE / LOKAL)          │
│  ├── users, refresh_tokens, campus_verification_codes  │
│  ├── deleted_user_tombstones, tombstone_identifiers    │
│  ├── vehicles, rides, scheduled_rides                  │
│  ├── ride_matches (Partial Indexes & Check Constraints)│
│  ├── pickup_checkins, no_show_reports, sanctions       │
│  ├── coin_ledger (APPEND-ONLY, Trigger Block Update)   │
│  ├── admin_audit_logs (APPEND-ONLY Trigger)            │
│  ├── coin_packages, topup_orders, system_configurations│
│  └── webhook_events (UNIQUE: gateway_name, event_id)   │
└────────────────────────────────────────────────────────┘
```

### Pemetaan Fase Pembuatan Tabel (Database Migration Schedule)
- **Fase 1a:** `users`, `refresh_tokens`, `system_configurations`.
- **Fase 1b:** `deleted_user_tombstones`, `tombstone_identifiers`, `campus_verification_codes`, `vehicles`, `coin_ledger` (beserta trigger Postgres anti-mutasi & partial index unik), `admin_audit_logs` (beserta trigger Postgres anti-mutasi).
- **Fase 2:** `rides`, `scheduled_rides`.
- **Fase 3:** `ride_matches` (dengan partial unique indexes, foreign key ganda, kolom `matched_at`, dan check constraints).
- **Fase 5:** `pickup_checkins`, `no_show_reports`, `sanctions`.
- **Fase 8:** `coin_packages`, `topup_orders`, `webhook_events`.

### Skema Tabel Database Lengkap (Semua Waktu Berbasis `TIMESTAMPTZ`)

1. **`users`:**
   - `id` (UUID, PK), `google_sub` (VARCHAR, UNIQUE, nullable on delete), `email` (VARCHAR, UNIQUE, nullable on delete), `phone_number` (VARCHAR, UNIQUE, nullable), `campus_email` (VARCHAR, UNIQUE, nullable), `full_name` (VARCHAR, nullable on delete), `campus_name` (VARCHAR, nullable on delete), `is_identity_verified` (BOOLEAN, default false), `campus_verified_at` (TIMESTAMPTZ, nullable), `campus_verification_method` (VARCHAR, nullable - `'GOOGLE_DOMAIN'` | `'EMAIL_OTP'`), `deleted_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
   - *Login Lookup:* Pencarian akun saat login dilakukan berdasarkan `google_sub`. Nilai `email` diperbarui dari verified ID token pada setiap login dan tidak menjadi primary identity key. Nilai `google_sub` diset NULL saat penghapusan akun (PII wipe).
   - *Aturan Pemblokiran Hapus Akun:* Operasi hapus akun ditolak keras jika pengguna:
     1. Memiliki saldo koin berbayar (`PAID > 0`, termasuk koin berbayar on-hold),
     2. Memiliki match aktif (`MATCHED`, `CONFIRMED`, `IN_PROGRESS`, `DISPUTED`, `NO_SHOW_REPORTED`),
     3. Memiliki laporan no-show yang masih terbuka (`PENDING_REVIEW`),
     4. Memiliki koin dalam status hold yang belum di-release (`HOLD_SERVICE_FEE` tanpa pasangan `RELEASE_HOLD`).
2. **`refresh_tokens` (Fase 1a):**
   - `id` (UUID, PK), `user_id` (UUID, FK users), `token_hash` (VARCHAR(64), UNIQUE - SHA-256), `family_id` (UUID), `expires_at` (TIMESTAMPTZ), `used_at` (TIMESTAMPTZ, nullable), `revoked_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
   - *Token Rotation & Reuse Detection:* Jika token yang `used_at != NULL` disajikan kembali, backend otomatis mencabut seluruh token dengan `family_id` yang sama (`revoked_at = NOW()`).
3. **`deleted_user_tombstones` & `tombstone_identifiers` (Fase 1b):**
   - `deleted_user_tombstones`: `id` (UUID, PK), `user_uuid_history` (UUID), `bonus_already_granted` (BOOLEAN), `sanction_ends_at` (TIMESTAMPTZ, nullable), `strike_dates_json` (JSONB, nullable - riwayat timestamp strike 90 hari terakhir), `expires_at` (TIMESTAMPTZ - retensi 1 tahun), `created_at` (TIMESTAMPTZ).
   - `tombstone_identifiers`: `id` (UUID, PK), `tombstone_id` (UUID, FK), `identifier_type` (`EMAIL`, `PHONE`, `CAMPUS_EMAIL`, `GOOGLE_SUB`), `identifier_hmac` (VARCHAR(64), UNIQUE - HMAC-SHA256).
   - *Aturan UPSERT Tombstone:* Jika pengguna menghapus akun dengan identitas yang sudah memiliki tombstone, record tombstone lama di-update: `expires_at` diperpanjang 1 tahun, `strike_dates_json` digabungkan, dan `sanction_ends_at` mengambil nilai terjauh.
   - *Normalisasi Identitas:* Identitas dibersihkan sebelum di-hash: `google_sub`, `email`, dan `campus_email` di-*trim* dan di-*lowercase*; nomor HP dikonversi ke format standar E.164 (misal: `+628...`). Rotasi `TOMBSTONE_HMAC_SECRET` akan memutus pencocokan identitas lama.
4. **`campus_verification_codes` (Fase 1b):**
   - `id` (UUID, PK), `user_id` (UUID, FK users), `campus_email` (VARCHAR), `code_hash` (VARCHAR(64)), `expires_at` (TIMESTAMPTZ - 10 menit), `attempts` (INTEGER, default 0, max 5 attempts), `consumed_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ). Dilengkapi pembatasan resend cooldown (60 detik) dan maksimum 5 kali percobaan per kode.
5. **`vehicles` (Fase 1b):**
   - `id` (UUID, PK), `user_id` (UUID, FK users), `vehicle_type` (VARCHAR, e.g. "Motor"), `vehicle_model` (VARCHAR, e.g. "Honda Vario Hitam"), `license_plate_masked` (VARCHAR, e.g. "*3821 AB"), `created_at` (TIMESTAMPTZ).
6. **`rides` (Fase 2):**
   - `id` (UUID, PK), `creator_id` (UUID, FK users), `scheduled_ride_id` (UUID, FK scheduled_rides, nullable), `role` (VARCHAR: `DRIVER`/`PASSENGER`), `origin_name` (VARCHAR), `origin_lat` (FLOAT), `origin_lon` (FLOAT), `dest_name` (VARCHAR), `dest_lat` (FLOAT), `dest_lon` (FLOAT), `departure_time` (TIMESTAMPTZ), `is_scheduled` (BOOLEAN), `cost_share_estimate` (INTEGER), `status` (VARCHAR: `OPEN`, `MATCHED`, `COMPLETED`, `CANCELLED`, `EXPIRED`), `created_at` (TIMESTAMPTZ).
7. **`scheduled_rides` (Fase 2):**
   - `id` (UUID, PK), `user_id` (UUID, FK users), `role` (VARCHAR), `days_of_week` (VARCHAR, e.g. "MON,TUE,WED,THU,FRI"), `departure_time_time` (TIME), `origin_lat` (FLOAT), `origin_lon` (FLOAT), `dest_lat` (FLOAT), `dest_lon` (FLOAT), `cost_share_estimate` (INTEGER), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
8. **`ride_matches` (Fase 3 - Master Lifecycle):**
   - `id` (UUID, PK), `driver_ride_id` (UUID, FK rides), `passenger_ride_id` (UUID, FK rides), `driver_id` (UUID, FK users), `passenger_id` (UUID, FK users), `status` (VARCHAR: `REQUESTED`, `MATCHED`, `CONFIRMED`, `IN_PROGRESS`, `COMPLETED`, `DISPUTED`, `NO_SHOW_REPORTED`, `NO_SHOW`, `CANCELLED`, `EXPIRED`), `matched_at` (TIMESTAMPTZ, nullable - diisi saat status menjadi MATCHED), `driver_confirmed_at` (TIMESTAMPTZ, nullable), `passenger_confirmed_at` (TIMESTAMPTZ, nullable), `driver_completed_at` (TIMESTAMPTZ, nullable), `passenger_completed_at` (TIMESTAMPTZ, nullable), `estimated_arrival_at` (TIMESTAMPTZ, nullable), `cancelled_by` (UUID, FK users, nullable), `cancelled_at` (TIMESTAMPTZ, nullable), `cancel_reason` (TEXT, nullable), `is_late_cancel` (BOOLEAN, default false), `dispute_reason` (TEXT, nullable), `dispute_deadline` (TIMESTAMPTZ, nullable - 72 jam), `expires_at` (TIMESTAMPTZ), `confirmation_deadline` (TIMESTAMPTZ), `created_at` (TIMESTAMPTZ).
   - *Integritas & Constraint Database:*
     ```sql
     ALTER TABLE ride_matches ADD CONSTRAINT chk_driver_passenger_distinct CHECK (driver_id <> passenger_id);

     ALTER TABLE ride_matches ADD CONSTRAINT chk_estimated_arrival_at 
     CHECK (status NOT IN ('IN_PROGRESS', 'COMPLETED', 'DISPUTED') OR estimated_arrival_at IS NOT NULL);

     CREATE UNIQUE INDEX uq_active_passenger_ride ON ride_matches (passenger_ride_id)
     WHERE status IN ('MATCHED', 'CONFIRMED', 'IN_PROGRESS', 'DISPUTED', 'NO_SHOW_REPORTED');

     CREATE UNIQUE INDEX uq_active_driver_ride ON ride_matches (driver_ride_id)
     WHERE status IN ('MATCHED', 'CONFIRMED', 'IN_PROGRESS', 'DISPUTED', 'NO_SHOW_REPORTED');

     CREATE UNIQUE INDEX uq_request_pair ON ride_matches (driver_ride_id, passenger_ride_id)
     WHERE status IN ('REQUESTED', 'REJECTED');
     ```
   - *Validasi Service Layer:* Backend memvalidasi mutlak: `driver_ride.role == 'DRIVER'`, `passenger_ride.role == 'PASSENGER'`, `driver_id == driver_ride.creator_id`, dan `passenger_id == passenger_ride.creator_id`.
9. **`pickup_checkins` (Fase 5):**
   - `id` (UUID, PK), `match_id` (UUID, FK ride_matches), `user_id` (UUID, FK users), `lat` (FLOAT, nullable on purge), `lon` (FLOAT, nullable on purge), `distance_to_pickup_m` (FLOAT - bukti permanen), `checked_in_at` (TIMESTAMPTZ - bukti permanen), `purge_after` (TIMESTAMPTZ - default `checked_in_at + INTERVAL '7 days'`).
10. **`no_show_reports` (Fase 5):**
    - `id` (UUID, PK), `match_id` (UUID, FK ride_matches), `reporter_id` (UUID, FK users), `reported_id` (UUID, FK users), `distance_meters` (FLOAT), `time_diff_seconds` (INTEGER), `reporter_lat` (FLOAT, nullable on purge), `reporter_lon` (FLOAT, nullable on purge), `status` (VARCHAR: `PENDING_REVIEW`, `VALIDATED`, `REJECTED`, `EXPIRED_AUTO_RELEASE`), `reporter_notes` (TEXT), `reported_clarification` (TEXT, nullable - hak klarifikasi terlapor), `admin_notes` (TEXT, nullable), `admin_id` (UUID, FK users, nullable), `review_deadline` (TIMESTAMPTZ - 72 jam), `purge_after` (TIMESTAMPTZ - default `review_deadline + INTERVAL '7 days'`), `resolved_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
    - *Constraint 1 Laporan Terbuka:*
      ```sql
      CREATE UNIQUE INDEX uq_one_pending_no_show_per_match ON no_show_reports (match_id)
      WHERE status = 'PENDING_REVIEW';
      ```
11. **`sanctions` (Fase 5):**
    - `id` (UUID, PK), `user_id` (UUID, FK users), `sanction_type` (VARCHAR: `WARNING`, `MATCHING_RESTRICTION_24H`, `SUSPEND_24H`, `SUSPEND_7D`, `ACCOUNT_REVIEW`), `reason` (TEXT), `starts_at` (TIMESTAMPTZ), `ends_at` (TIMESTAMPTZ), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
    - Status suspensi/restriksi pengguna diturunkan langsung dari query baris sanksi aktif (`WHERE user_id = :uid AND is_active = true AND ends_at > NOW()`).
12. **`admin_audit_logs` (Fase 1b - Append-Only dengan Trigger Anti-Mutasi):**
    - `id` (UUID, PK), `admin_user_id` (UUID, FK users), `admin_email` (VARCHAR - snapshot email saat aksi), `action_type` (VARCHAR: `ADMIN_ADJUSTMENT`, `RESOLVE_DISPUTE`, `VALIDATE_NO_SHOW`, `REJECT_NO_SHOW`, `MANUAL_REFUND`), `target_user_id` (UUID, nullable), `reference_id` (UUID, nullable), `reason` (TEXT), `ip_address` (VARCHAR), `created_at` (TIMESTAMPTZ).
    - *Trigger Mutasi:* `trg_prevent_admin_audit_logs_mutation` menolak keras `UPDATE` dan `DELETE`.
13. **`coin_ledger` (Fase 1b - Append-Only dengan Trigger Anti-Mutasi & Anti-Hold Ganda):**
    - `id` (UUID, PK), `user_id` (UUID, FK users), `transaction_type` (VARCHAR: `BONUS`, `TOPUP_PAID`, `HOLD_SERVICE_FEE`, `RELEASE_HOLD`, `SERVICE_FEE`, `REFUND`, `ADMIN_ADJUSTMENT`), `amount` (INTEGER, positif/negatif), `coin_category` (VARCHAR: `BONUS`, `PAID`), `reference_id` (UUID), `reference_type` (VARCHAR: `RIDE_MATCH`, `TOPUP_ORDER`, `ADMIN_ACTION`, `SIGNUP_REWARD`), `idempotency_key` (VARCHAR, UNIQUE), `created_at` (TIMESTAMPTZ), `actor` (VARCHAR).
    - *Index Unik Parsial Pencegah Hold Ganda:*
      ```sql
      CREATE UNIQUE INDEX uq_coin_ledger_hold_prevent 
      ON coin_ledger (reference_type, reference_id, user_id, transaction_type) 
      WHERE transaction_type IN ('HOLD_SERVICE_FEE', 'RELEASE_HOLD', 'SERVICE_FEE');
      ```
    - *Trigger Mutasi:* `trg_prevent_coin_ledger_mutation` menolak keras `UPDATE` dan `DELETE`.
14. **`coin_packages` & `topup_orders` (Fase 8):**
    - `coin_packages`: `id` (UUID, PK), `package_code` (VARCHAR, UNIQUE), `coin_amount` (INTEGER), `price_idr` (INTEGER), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
    - `topup_orders`: `id` (UUID, PK), `order_number` (VARCHAR, UNIQUE), `user_id` (UUID, FK users), `package_id` (UUID, FK coin_packages), `amount_idr` (INTEGER), `paid_amount_idr` (INTEGER, nullable), `refunded_amount_idr` (INTEGER, default 0), `coins_to_credit` (INTEGER), `status` (VARCHAR: `PENDING`, `PAID`, `EXPIRED`, `FAILED`, `REFUNDED`, `REFUND_REQUIRED`, `REVIEW_REQUIRED`, `PARTIALLY_REFUNDED`), `payment_link` (TEXT, nullable), `gateway_reference` (VARCHAR, nullable), `expires_at` (TIMESTAMPTZ), `paid_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
15. **`webhook_events` & `system_configurations`:**
    - `webhook_events`: `id` (UUID, PK), `gateway_name` (VARCHAR), `event_id` (VARCHAR), `order_number` (VARCHAR), `signature` (VARCHAR), `payload_json` (JSONB, nullable on purge), `processed_at` (TIMESTAMPTZ), `status` (VARCHAR: `PROCESSED`, `IGNORED`, `FAILED`), `expires_at` (TIMESTAMPTZ - retensi 90 hari). Constraint: `UNIQUE(gateway_name, event_id)`.
    - `system_configurations`: `key` (VARCHAR, PK), `value` (VARCHAR), `description` (TEXT), `updated_at` (TIMESTAMPTZ). Nilai konfigurasi:
      - `MAX_TOPUP_PER_TX_IDR=100000`
      - `MAX_USER_BALANCE_COINS=200`
      - `INITIAL_BONUS_COINS=30`
      - `ALLOWED_CAMPUS_DOMAINS=ui.ac.id,ugm.ac.id,itb.ac.id`
      - `MATCH_OVERLAP_MINUTES=90`
      - `REOPEN_MIN_LEAD_MINUTES=30`
      - `REQUEST_RESPONSE_MINUTES=30`
      - `CONFIRMATION_WINDOW_MINUTES=60`
      - `MIN_CONFIRMATION_LEAD_MINUTES=15`
      - `MIN_REQUEST_LEAD_MINUTES=45`
    - *Validasi Invarian Konfigurasi Sistem:* Saat sistem memuat konfigurasi, service layer memvalidasi secara ketat bahwa:
      $$\text{REOPEN\_MIN\_LEAD\_MINUTES} \ge \text{MIN\_CONFIRMATION\_LEAD\_MINUTES}$$
      (default: $30 \ge 15$). Jika konfigurasi melanggar aturan ini, sistem menolak startup/memperbarui data atau melakukan *clamping* otomatis demi menjamin tersedianya batas waktu minimal 15 menit untuk konfirmasi.
    - *Aturan Perhitungan Batas Waktu Dinamis (Membaca system_configurations):*
      - `expires_at = LEAST(created_at + INTERVAL '1 minute' * REQUEST_RESPONSE_MINUTES, departure_time - INTERVAL '1 minute' * REOPEN_MIN_LEAD_MINUTES)`
      - `confirmation_deadline = LEAST(matched_at + INTERVAL '1 minute' * CONFIRMATION_WINDOW_MINUTES, departure_time - INTERVAL '1 minute' * MIN_CONFIRMATION_LEAD_MINUTES)`
      - *Validasi Lead Time:* Pembuatan request baru wajib ditolak jika sisa waktu menuju keberangkatan $< \text{MIN\_REQUEST\_LEAD\_MINUTES}$ (default 45 menit).
    - *Aturan Mutlak Environment Variables:* `TOPUP_ENABLED`, `PAYMENT_ENV`, `ADMIN_EMAILS`, `TOMBSTONE_HMAC_SECRET`, `SERVICE_FEE_COINS`, dan `CRON_SECRET` dilarang disimpan di tabel database; murni dibaca dari Environment Variable sistem (`.env`).
    - *Nilai `SERVICE_FEE_COINS`:* Default 1; bernilai 0 pada mode pilot-lite (tidak ada baris `HOLD_SERVICE_FEE`, `RELEASE_HOLD`, atau `SERVICE_FEE` yang ditulis, dan pengecekan saldo $\ge 1$ koin saat konfirmasi dilewati).

---

## 4. Tabel Tugas Pembersih Berkala (*Background Sweeper Tasks*)

Hosting gratis dapat tidur (*sleep*), sehingga seluruh tugas dirancang **idempotent, catch-up safe, dan dieksekusi secara lazy saat request tiba**, didukung oleh pemanggilan cron eksternal gratis (cron-job.org / GitHub Actions) pada endpoint internal `POST /internal/sweeper/run` yang diamankan header rahasia dari environment variable `CRON_SECRET`.

| No | Nama Tugas | Kondisi Pemicu (Trigger) | Aksi Database (Action) | Catatan Idempotensi & Keamanan |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Match REQUESTED Expiry** | `ride_matches.status = 'REQUESTED' AND expires_at < NOW()` | Update match $\rightarrow$ `EXPIRED`. Status ride tidak diubah (tetap `OPEN`; jika waktu lewat, ditangani task 6). | Klausa `FOR UPDATE SKIP LOCKED`. Idempotent (status terminal `EXPIRED`). |
| 2 | **Confirmation Deadline Expiry** | `ride_matches.status = 'MATCHED' AND confirmation_deadline < NOW()` | Update match $\rightarrow$ `EXPIRED`. Panggil `on_expired()`: jika ada pihak sempat konfirmasi, catat `RELEASE_HOLD` (+1). Kasus 1 pihak: ride pihak tak konfirmasi $\rightarrow$ `CANCELLED`, ride pihak konfirmasi mengikuti lead time ($\ge 30$ mnt $\rightarrow$ `OPEN`, else `EXPIRED`). Kasus 0 pihak: kedua ride ikuti lead time. | Menggunakan `idempotency_key` release hold. Aman dijalankan berulang. |
| 3 | **IN_PROGRESS Auto-Complete** | `ride_matches.status = 'IN_PROGRESS' AND ((driver_completed_at IS NOT NULL AND driver_completed_at + INTERVAL '60 min' < NOW()) OR (COALESCE(estimated_arrival_at, departure_time + INTERVAL '3 hours') + INTERVAL '2 hours' < NOW()))` | Update match $\rightarrow$ `COMPLETED`. Panggil `on_completed()`: eksekusi `RELEASE_HOLD` (+1) lalu `SERVICE_FEE` (-1) per pihak (jika fee > 0). Update status kedua ride $\rightarrow$ `COMPLETED`. | Ditransaksikan atomik per match; dicegah jika ada sanggahan terbuka. |
| 4 | **DISPUTED 72h Auto-Release** | `ride_matches.status = 'DISPUTED' AND dispute_deadline < NOW()` | Update match $\rightarrow$ `CANCELLED`. Eksekusi `RELEASE_HOLD` (+1) kedua pihak tanpa fee. Update kedua ride $\rightarrow$ `CANCELLED`. | Batas waktu 72 jam pasti. Mencegah koin pengguna tertahan selamanya. |
| 5 | **NO_SHOW_REPORTED 72h Auto-Release** | `ride_matches.status = 'NO_SHOW_REPORTED'` JOIN `no_show_reports` ON `no_show_reports.match_id = ride_matches.id AND no_show_reports.review_deadline < NOW()` | Update match $\rightarrow$ `CANCELLED`, laporan $\rightarrow$ `EXPIRED_AUTO_RELEASE`. Eksekusi `RELEASE_HOLD` (+1) kedua pihak (tanpa sanksi). Update ride $\rightarrow$ `CANCELLED`. | Melindungi hak pengguna jika admin lalai meninjau laporan no-show. |
| 6 | **Rides OPEN Expiry** | `rides.status = 'OPEN' AND departure_time < NOW()` | Update status ride $\rightarrow$ `EXPIRED`. | Dijalankan lazy saat pencarian rute & sweeper berkala. |
| 7 | **Topup PENDING Expiry** | `topup_orders.status = 'PENDING' AND expires_at < NOW()` | Update status order $\rightarrow$ `EXPIRED`. | Jika ada late payment webhook tiba nanti, ditangani oleh transisi khusus. |
| 8 | **GPS 7-Day Purge** | `(pickup_checkins.purge_after < NOW() OR no_show_reports.purge_after < NOW()) AND match.status NOT IN ('DISPUTED', 'NO_SHOW_REPORTED')` | Set `lat = NULL`, `lon = NULL`, `reporter_lat = NULL`, `reporter_lon = NULL`. Ringkasan bukti jarak & waktu tetap utuh. | Juga dievaluasi lazy saat endpoint audit membaca data GPS yang kedaluwarsa. |
| 9 | **Webhook Payload 90-Day Purge** | `webhook_events.expires_at < NOW() AND payload_json IS NOT NULL` | Set `payload_json = NULL`. Metadata event, signature, order_number tetap dipertahankan. | Menghemat kapasitas database PostgreSQL 8 GB / cloud free tier. |
| 10| **Tombstone 1-Year Expiry** | `deleted_user_tombstones.expires_at < NOW()` | Hapus baris di `deleted_user_tombstones` dan `tombstone_identifiers` secara berantai (cascade). | Kepatuhan prinsip batasan penyimpanan data pribadi (UU PDP). |
| 11| **Expired Refresh Token Cleanup** | `expires_at < NOW() OR (revoked_at IS NOT NULL AND revoked_at < NOW() - INTERVAL '30 days')` | Hapus baris token yang telah kedaluwarsa atau dicabut dari tabel `refresh_tokens`. | Mencegah penumpukan tabel token autentikasi. |

---

## 5. Rumus Float Koin Berbayar Komprehensif (Bank Indonesia Compliance)

Total liabilitas rupiah atas dana float dihitung secara sistemik dari seluruh pengguna:
$$\text{Harga Rata-Rata per Koin} = \begin{cases} \frac{\sum \text{paid\_amount\_idr pesanan PAID}}{\sum \text{coins\_to\_credit pesanan PAID}}, & \text{jika } \sum \text{coins\_to\_credit} > 0 \\ 0, & \text{jika belum ada pesanan PAID} \end{cases}$$
$$\text{Float Koin Aktif} = \text{Harga Rata-Rata} \times (\text{Sisa Saldo Koin Berbayar} + \text{Koin Berbayar On-Hold})$$
$$\text{Total Nilai Float} = \text{Float Koin Aktif} + \sum \text{paid\_amount\_idr (REFUND\_REQUIRED)} + \sum \text{paid\_amount\_idr (REVIEW\_REQUIRED)}$$
- Pesanan `REFUNDED` dikeluarkan sepenuhnya dari hitungan float.
- Ambang batas acuan Bank Indonesia: Rp1.000.000.000,- (diverifikasi di `COMPLIANCE_CHECKLIST.md`).
- Indikator Peringatan Dini: Kuning ($\ge 30\%$) dan Merah ($\ge 60\%$).

---

## 6. Rencana Pengembangan Bertahap (Satu Fase Per Respons)

### Fase 1a: Fondasi Monorepo, Database Ringan, Google Login, & Token Family
- **Fokus:** Setup monorepo (`backend/` FastAPI & `mobile/` Flutter).
- **Database:** Setup PostgreSQL ringan + migrasi tabel `users` (dengan kolom `google_sub`, `campus_verified_at`, `campus_verification_method`), `refresh_tokens`, dan `system_configurations`.
- **Fitur:** Login Google OAuth dengan verifikasi ID Token JWT di backend (`email_verified == true`). Pencarian akun login dilakukan melalui `google_sub` (bukan email). Email diperbarui dari token pada tiap login. Pencocokan domain kampus dot-boundary (`domain == allowed || domain.endswith("." + allowed)`). Helper `is_admin_email()` via parsing `ADMIN_EMAILS`. Rotasi refresh token dengan deteksi reuse token family, dan rate limiting dasar pada endpoint auth.
- **Pengujian:** Verifikasi token JWT Google, uji login lookup via `google_sub`, uji reuse detection refresh token (seluruh family dicabut), uji rate limiter auth, dan uji dot-boundary whitelist.

### Fase 1b: Verifikasi Identitas, Kendaraan, Bonus Awal, & Immutability Ledger
- **Fokus:** Pengikatan identitas kampus, inisialisasi ledger keuangan, dan log audit admin.
- **Database:** Migrasi tabel `deleted_user_tombstones`, `tombstone_identifiers`, `campus_verification_codes`, `vehicles`, `coin_ledger`, dan `admin_audit_logs`. Pemasangan trigger Postgres anti-mutasi `trg_prevent_coin_ledger_mutation` dan `trg_prevent_admin_audit_logs_mutation`, serta index unik `uq_coin_ledger_hold_prevent`.
- **Fitur:** 
  - Verifikasi email kampus Jalur A (Google ID Token, primer, 100% gratis). Jalur B (One-time code email via `campus_verification_codes`, kedaluwarsa 10 menit, max 5 attempts) bersifat cadangan dan dibangun hanya jika pengujian akun mahasiswa asli menunjukkan kampus tidak login via Google. Penyedia email Jalur B divalidasi di Fase 1b dengan mempertimbangkan syarat kepemilikan domain.
  - Nilai `is_identity_verified = true` dan `campus_verified_at = NOW()` diupdate bersamaan dalam satu transaksi atomik.
  - Pencatatan 30 koin bonus awal via `coin_ledger` hanya jika verifikasi kampus sukses dan tidak ditemukan kecocokan identitas di tabel tombstone. Jika identitas cocok dengan tombstone aktif, pendaftaran tetap diizinkan tetapi bonus tidak diberikan, serta sanksi aktif dan strike 90 hari terakhir dipulihkan.
  - Input kendaraan dengan plat nomor tersamar (`*3821 AB`).
- **Pengujian:** Uji trigger Postgres menolak `UPDATE`/`DELETE` pada ledger dan log audit admin, uji indeks unik anti-hold ganda, uji tombstone HMAC-SHA256 menolak bonus ganda pasca hapus akun tanpa memblokir sign-up baru, dan uji validasi OTP email kampus.

### Fase 2: Manajemen Perjalanan & Koordinat Rute
- **Fokus:** Pembuatan rute tumpangan *on-demand* dan pola jadwal rutin (Senin–Jumat).
- **Database:** Migrasi tabel `rides` (termasuk `scheduled_ride_id`) dan `scheduled_rides`.
- **Fitur:** Input asal, tujuan, waktu, estimasi biaya bersama. Peta OpenStreetMap (flutter_map). Pemilik dapat membatalkan rute (`OPEN` $\rightarrow$ `CANCELLED`). Rute dan jadwal bersifat immutable jika terdapat match non-terminal.
- **Pengujian:** Validasi input koordinat, query filter perjalanan aktif, pembatalan ride mandiri, kalkulasi jarak rute Haversine/OSRM.

### Fase 3: Matching Engine, Dynamic Lazy Timeout, & Time-Overlap Check
- **Fokus:** Algoritma scoring (Rute 35%, Jarak Jemput 25%, Waktu 25%, Biaya 15%).
- **Database:** Migrasi tabel `ride_matches` (dengan kolom `matched_at`, partial unique indexes, constraint `driver_id <> passenger_id`, constraint `estimated_arrival_at`, dan index `uq_request_pair`).
- **Fitur:** Pemilihan Passenger oleh Driver dengan penguncian atomik `SELECT ... FOR UPDATE`. Penerimaan ajakan perjalanan otomatis membatalkan tawaran `REQUESTED` lain (`SUPERSEDED`) dan menolak jika pengguna memiliki match aktif yang bertabrakan waktu (`MATCH_OVERLAP_MINUTES`).
- **Pengujian:** Bobot scoring, uji balapan dua driver memilih passenger yang sama (verifikasi partial index), uji penolakan time-overlap match, uji pembatalan otomatis match tersaingi (*superseded*), uji index `uq_request_pair` menolak request ulang pasangan yang pernah ditolak namun mengizinkan pasangan yang expired, uji validasi pemuatan konfigurasi sistem (`REOPEN_MIN_LEAD_MINUTES >= MIN_CONFIRMATION_LEAD_MINUTES`), serta uji formula batas waktu dinamis (`expires_at` dan `confirmation_deadline` berbasis departure_time dan konfigurasi).

### Fase 4: Siklus Status Perjalanan & Lifecycle Hooks
- **Fokus:** State machine transisi lengkap `ride_matches` dan `rides`.
- **Fitur:**
  - Lifecycle hooks: `on_party_confirmed(user_id)`, `on_expired()`, `on_no_show()`, `on_completed()`, dan `on_cancelled()` (awalnya no-op).
  - Pemicu tunggal `IN_PROGRESS` saat Driver menekan tombol "Mulai Perjalanan" (disertai pengisian `estimated_arrival_at`).
  - Logika penyelesaian: jika passenger klik selesai lebih awal langsung `COMPLETED`; jendela 60 menit pasca Driver klik selesai; ATAU auto-complete $ETA + 2\text{ jam}$.
  - Pembatalan pra-jalan (rekan kembali `OPEN` jika sisa waktu $\ge \text{REOPEN\_MIN\_LEAD\_MINUTES}$, selain itu `EXPIRED`) vs pembatalan saat `IN_PROGRESS` (kedua ride `CANCELLED`).
  - Penanganan kedua pihak gagal konfirmasi (keduanya dicek lead time-nya).
- **Pengujian:** Uji passenger klik selesai awal, uji batas waktu pembukaan ulang $\ge 30$ menit, uji transisi darurat di jalan, uji transisi `DISPUTED` 72 jam auto-release.

### Fase 5: Keamanan, Penanganan No-Show, & Admin Router
- **Fokus:** Kehadiran fisik titik jemput, hak klarifikasi, dan penanganan sengketa.
- **Database:** Migrasi tabel `pickup_checkins`, `no_show_reports`, dan `sanctions`.
- **Fitur:** Tombol *"Saya sudah di titik jemput"* mencatat baris di `pickup_checkins` dengan toleransi 10 menit. Laporan `NO_SHOW_REPORTED` (maksimal 1 laporan aktif per match). Penyediaan hak klarifikasi tertulis bagi pihak terlapor. Batas waktu review admin 72 jam; jika lewat atau laporan ditolak (Opsi A), hold koin otomatis di-release tanpa sanksi. Akumulasi sanksi event-based 90 hari dan sanksi `MATCHING_RESTRICTION_24H` untuk 3 kali pembatalan telat. Router `/api/v1/admin` terisolasi dengan rate limiting dan guard `is_admin_email()`.
- **Pengujian:** Validasi radius GPS titik jemput, hak klarifikasi terlapor, partial unique index 1 laporan terbuka per match, sanksi pembatalan telat berbasis event, auto-release saat admin timeout 72 jam.

### Fase 5.5: Privacy Pack (Prasyarat Wajib Sebelum Pilot-Lite)
- **Fokus:** Kepatuhan hukum perlindungan data pribadi dan sanitasi data sensitif sebelum aplikasi diakses pengguna nyata di kampus.
- **Fitur:**
  - Penyusunan Draf Kebijakan Privasi & Syarat Ketentuan dasar.
  - Tampilan formulir persetujuan (*consent screen*) pelacakan lokasi GPS di aplikasi mobile.
  - Aktivasi job pembersihan retensi data GPS (sweeper 7 hari) yang membekukan penghapusan jika ada sengketa aktif.
  - Alur penghapusan akun (*Right to be Forgotten*) dengan aturan pemblokiran ketat (saldo koin berbayar, match aktif, laporan terbuka, atau hold aktif) serta penulisan tombstone UPSERT ber-HMAC-SHA256.
- **Pengujian:** Uji pemblokiran hapus akun saat ada saldo berbayar atau match aktif, uji pembersihan koordinat GPS menjadi NULL setelah 7 hari, dan uji freeze GPS saat ada sengketa.

*(Milestone: Pilot-Lite)*
> [!NOTE]
> Setelah Fase 5.5 selesai secara sempurna, aplikasi siap diluncurkan dalam mode **Pilot-Lite** (`SERVICE_FEE_COINS=0`, tanpa pemotongan koin layanan). Bonus 30 koin tetap tercatat di ledger sebagai saldo awal, namun perjalanan tidak memotong koin sehingga mahasiswa dapat menguji kecocokan rute dan interaksi penjemputan secara nyata tanpa risiko keuangan.

### Fase 6: Dompet Koin Tertutup (Bonus-Only, Hold/Settle Atomik)
- **Fokus:** Penyambungan lifecycle hooks Fase 4 ke ledger koin.
- **Fitur:**
  - Hold koin per pihak saat klik konfirmasi; auto-release jika gagal capai `CONFIRMED` sampai deadline.
  - Kunci baris users dengan urutan `user_id` menaik anti-deadlock (`ORDER BY id ASC`).
  - Settle atomik saat `COMPLETED`: `RELEASE_HOLD` (+1) dan `SERVICE_FEE` (-1) dengan `coin_category` identik.
  - Transaksi `ADMIN_ADJUSTMENT` wajib alasan dan log audit `admin_audit_logs` atomik.
- **Pengujian Wajib:**
  - Double tap konfirmasi dengan saldo berubah tetap menghasilkan tepat 1 baris hold.
  - Dua konfirmasi bersamaan dengan saldo pas-pasan tidak membuat saldo negatif (row locking).
  - Satu pihak gagal konfirmasi $\rightarrow$ hold pihak lain otomatis di-release.
  - Total potongan perjalanan sukses tepat 1 koin per pihak.
  - Koin bonus terpakai sebelum koin berbayar.
  - Uji deadlock multi-transaksi dengan retry backoff.

### Fase 7: Pengujian Terpadu & Simulasi Pilot Kampus Lengkap
- **Fokus:** Validasi end-to-end simulasi alur operasional kampus dengan sistem dompet aktif.
- **Fitur:** Simulasi komprehensif skenario multi-pengguna: pendaftaran, verifikasi kampus, matching konkuren, check-in GPS, penyelesaian perjalanan, dan resolusi sengketa admin.
- **Pengujian:** Stress testing ringan alur transaksi dan penanganan error jaringan pada laptop 8 GB.

### Fase 8: Modul Pembayaran Sandbox, Kepatuhan Fintech, & Laporan Float
- **Fokus:** Integrasi sandbox payment gateway untuk pembelian paket koin.
- **Database:** Migrasi tabel `coin_packages`, `topup_orders`, dan `webhook_events`.
- **Pengaturan:** `TOPUP_ENABLED=false` (default) & `PAYMENT_ENV=sandbox` (Environment Variables murni).
- **Fitur:**
  - Penanganan pesanan kedaluwarsa yang dibayar (kredit jika $\le$ saldo max, tandai `REFUND_REQUIRED` jika melebihi batas).
  - Penanganan selisih nominal bayar $\rightarrow$ status `REVIEW_REQUIRED` dengan alur keluar admin (`PAID`, `REFUND_REQUIRED`, `REFUNDED`).
  - Penanganan pengembalian dana parsial (`PARTIALLY_REFUNDED`).
  - Laporan float rupiah aktual komprehensif dengan penanganan pembagian nol dan peringatan dini 30% dan 60% ambang batas BI.
  - Job rekonsiliasi harian internal database vs laporan gateway.
- **Gerbang Go-Live Produksi:** Checklist audit hukum, tinjauan ahli kode pembayaran, persetujuan merchant gateway, dan verifikasi kebijakan toko aplikasi.
- **Pengujian Wajib:**
  - Webhook dikirim 3 kali (uji idempotency).
  - Webhook signature salah / dimanipulasi.
  - Nominal bayar tidak cocok $\rightarrow$ order menjadi `REVIEW_REQUIRED`.
  - Rate limiting endpoint login dan topup.

---

## 7. Catatan Desain Fase 8 (Belum Diputuskan)

Bagian ini mencatat detail arsitektur pembayaran yang sengaja ditangguhkan hingga Fase 8:
1. **Transisi Keluar dari `PARTIALLY_REFUNDED`:** Apakah pesanan berstatus `PARTIALLY_REFUNDED` merupakan status terminal (akhir), atau dapat mengalami refund sisa lanjutan hingga menjadi `REFUNDED` penuh?
2. **Formula Float dengan Refund Parsial:** Rumus rata-rata harga per koin harus memperhitungkan pengurangan nilai nominal rupiah (`paid_amount_idr - refunded_amount_idr`) dibagi sisa koin berbayar awal yang belum ter-refund, agar angka float tidak terdistorsi.
3. **Perhitungan Nilai Refund Paket yang Terpakai Sebagian:** Jika pengguna membeli paket 50 koin seharga Rp20.000 (Rp400/koin) dan telah memakai 20 koin, pengembalian dana atas sisa 30 koin dihitung proporsional murni ($30 \times \text{Rp}400 = \text{Rp}12.000$) dikurangi biaya administrasi gateway (jika ada).

---

## 8. Pertanyaan untuk Konsultasi Hukum (Legal Compliance Checklist)

Sebelum melangkah ke aktivasi produksi (`PAYMENT_ENV=production`), daftar pertanyaan berikut **wajib dijawab dan disetujui** oleh konsultan hukum fintech & privasi data independen:
1. **UU Pelindungan Data Pribadi (UU PDP):** Apakah penyimpanan riwayat hash identitas (`tombstone_identifiers` via HMAC-SHA256) selama 1 tahun pasca penghapusan akun memenuhi ketentuan *pseudonymization* yang sah untuk tujuan pencegahan fraud/sanksi, dan bagaimana status penautan `user_uuid_history` terhadap riwayat ledger anonim?
2. **Ketentuan Uang Elektronik Closed-Loop Bank Indonesia (Pasca 31 Maret 2026):** Berdasarkan pembaruan regulasi sistem pembayaran Bank Indonesia, apakah model koin tertutup Ajun murni berstatus *closed-loop* non-PJP, berapa batas pasti akumulasi dana float yang mewajibkan pelaporan berkala ke BI, dan apakah dana float wajib ditempatkan pada rekening *escrow* terpisah?
3. **Kebijakan Pembayaran Toko Aplikasi (Google Play Store & Apple App Store):** Apakah penjualan koin biaya layanan pencocokan tumpangan fisik antarmahasiswa dikategorikan sebagai *in-app digital goods* yang wajib menggunakan Google Play Billing (komisi 15–30%), atau dapat dikecualikan sebagai *facilitation of real-world physical services* sehingga legal menggunakan payment gateway pihak ketiga (Midtrans/Xendit)?
4. **Syarat & Ketentuan Merchant Payment Gateway:** Apakah badan usaha/organisasi mahasiswa pengelola Ajun memenuhi syarat kepatuhan *Know Your Business* (KYB) merchant gateway untuk kategori platform agregator/matching komunitas?

---

## 9. Hasil Pemeriksaan Konsistensi (Self-Consistency Cross-Check)

Berikut adalah pemeriksaan konsistensi faktual yang benar-benar diverifikasi pada dokumen v1.7.1:
1. **Verifikasi `SUPERSEDED`:** Dipastikan bahwa `SUPERSEDED` **bukanlah** nilai enum status pada `ride_matches`, melainkan nilai string pada kolom `cancel_reason` saat status match menjadi `CANCELLED`.
2. **Pemeriksaan Skema Kolom Baru:** Kolom `google_sub`, `campus_verified_at`, dan `campus_verification_method` telah tercantum di tabel `users` (Bagian 3) dan diintegrasikan pada alur login Fase 1a dan verifikasi Fase 1b secara atomik.
3. **Pemeriksaan Tabel `campus_verification_codes`:** Tabel telah didefinisikan lengkap dengan kolom limit attempts, serta dicantumkan pada skema database, jadwal migrasi (Fase 1b), dan diagram arsitektur.
4. **Pemeriksaan Aturan Mutlak Environment Variables:** Diverifikasi bahwa 6 variabel lingkungan (`TOPUP_ENABLED`, `PAYMENT_ENV`, `ADMIN_EMAILS`, `TOMBSTONE_HMAC_SECRET`, `SERVICE_FEE_COINS`, `CRON_SECRET`) tercantum eksplisit sebagai variabel yang dilarang berada di database.
5. **Pemeriksaan Indeks & Constraint:** Diverifikasi keberadaan partial unique index `uq_request_pair` (hanya `REQUESTED` dan `REJECTED`, sehingga `EXPIRED` pair dapat di-request ulang), partial index `uq_active_passenger_ride` / `uq_active_driver_ride`, serta constraint `chk_estimated_arrival_at` dan `chk_driver_passenger_distinct`.
6. **Pemeriksaan Kolom `matched_at` & Formula Waktu Dinamis:** Kolom `matched_at` telah ditambahkan ke skema `ride_matches`, dan formula dinamis `expires_at` serta `confirmation_deadline` telah diverifikasi membaca konfigurasi waktu dari `system_configurations` dengan syarat minimal 15 menit waktu konfirmasi.
7. **Pemeriksaan Invarian Konfigurasi Sistem:** Aturan validasi $\text{REOPEN\_MIN\_LEAD\_MINUTES} \ge \text{MIN\_CONFIRMATION\_LEAD\_MINUTES}$ telah diverifikasi di Bagian 3 dan ditambahkan ke daftar pengujian Fase 3.
8. **Pemeriksaan Alur Sweeper Task 2 & 5:** Task 2 telah diverifikasi menangani pemisahan pembatalan ride pihak yang tidak konfirmasi, dan Task 5 telah diverifikasi melakukan join eksplisit ke `no_show_reports` untuk membaca `review_deadline`.
9. **Pemeriksaan Gerbang Produksi:** Penegasan bahwa pertanyaan hukum di Bagian 8 wajib terjawab sebelum `PAYMENT_ENV=production` telah ditegaskan secara eksplisit.
