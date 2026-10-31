# Ajun (Antar Jemput Universitas) - Implementation Plan (Revisi v1.7 - Final Standalone)

Dokumen spesifikasi teknis dan rencana implementasi menyeluruh untuk aplikasi **Ajun (Antar Jemput Universitas)**. Dirancang untuk pencocokan tumpangan sesama mahasiswa (*peer-to-peer ride matching*) dengan rute dan jadwal bersama, verifikasi titik jemput, sistem akuntansi dompet tertutup (*closed-loop immutable ledger*) dengan *hold/release/settle* atomik, row-level locking anti-deadlock, dan arsitektur backend hemat sumber daya (*RAM 8 GB friendly*).

---

## Ringkasan Perubahan (v1.6 $\rightarrow$ v1.7)

1. **Pemulihan Tabel Transisi `rides`:** Tabel transisi status `rides` dipulihkan secara eksplisit (`OPEN`, `MATCHED`, `COMPLETED`, `CANCELLED`, `EXPIRED`) dengan pengendali utama pada `ride_matches.status`.
2. **Pembatalan Ajakan Tersaingi (*Superseded Match*):** Saat Passenger menerima tawaran (`REQUESTED` $\rightarrow$ `MATCHED`), seluruh match lain berstatus `REQUESTED` pada `passenger_ride_id` atau `driver_ride_id` otomatis dibatalkan dalam transaksi yang sama (`CANCELLED`, `cancel_reason = 'SUPERSEDED'`) tanpa efek ke ledger.
3. **Pencegahan Tumpang-Tindih Waktu Pengguna (*Time Overlap Check*):** Penambahan validasi transaksi terkunci untuk menolak match jika pengguna telah memiliki match aktif lain dalam rentang waktu yang bertabrakan (parameter `MATCH_OVERLAP_MINUTES`, default 90 menit).
4. **Pemberlakuan Batas Waktu Pembukaan Ulang (*Reopen Lead Time*):** Jika konfirmasi gagal atau match dibatalkan sebelum jalan, ride rekan hanya dibuka kembali ke `OPEN` jika selisih waktu menuju keberangkatan $\ge \text{REOPEN\_MIN\_LEAD\_MINUTES}$ (default 30 menit); jika kurang, ride otomatis menjadi `EXPIRED`.
5. **Standarisasi Waktu Universal ke `TIMESTAMPTZ`:** Seluruh kolom waktu database menggunakan `TIMESTAMPTZ` (disimpan dalam UTC), dan antarmuka API menggunakan format standar ISO-8601 UTC.
6. **Tabel `refresh_tokens` & Deteksi *Reuse* di Fase 1a:** Dibuat tabel `refresh_tokens` dengan mekanisme rotasi token family; jika token yang sudah terpakai disajikan kembali, seluruh *token family* dicabut seketika demi keamanan.
7. **Aturan Pemblokiran Hapus Akun yang Diperketat:** Penghapusan akun diblokir jika salah satu terpenuhi: koin berbayar (`PAID`) $> 0$, memiliki match aktif, memiliki laporan no-show terbuka, atau memiliki koin dalam status hold yang belum di-release.
8. **Tombstone Idempotent (UPSERT) & Normalisasi Identitas:** Penulisan tombstone menggunakan mekanisme `UPSERT` untuk mencegah pelanggaran unique constraint pada penghapusan akun berulang; pencocokan sign-up menggunakan identitas yang dinormalisasi (lowercase, trim, format E.164) dengan HMAC-SHA256 ber-secret key.
9. **Spesifikasi Lengkap Tabel Tugas Pembersih (*Sweeper Tasks*):** Disusun tabel komprehensif 11 tugas otomatis yang idempotent, catch-up safe, dijalankan secara *lazy* saat baca data dan dipicu oleh *cron endpoint* terproteksi rahasia (`X-Internal-Cron-Secret`).
10. **Penyempurnaan Skema GPS & Retensi:** Kolom koordinat (`lat`, `lon`) pada `pickup_checkins` dan `no_show_reports` dibuat nullable untuk dihapus (diset `NULL`) setelah `purge_after` (7 hari), sementara ringkasan bukti (*evidence summary*: jarak meter & waktu) dipertahankan permanen.
11. **Dua Jalur Verifikasi Kampus di Fase 1b:** Jalur A (Google ID Token domain whitelist, 100% gratis) sebagai jalur utama; Jalur B (One-time code via SMTP institusi, kedaluwarsa 10 menit) sebagai cadangan gratis jika kampus tidak menggunakan Google Workspace.
12. **Model Data Pembatalan Telat (*Late Cancellation*):** Penambahan kolom `is_late_cancel` BOOLEAN pada `ride_matches` dan sanksi `MATCHING_RESTRICTION_24H` jika pengguna melakukan pembatalan telat $\ge 3$ kali dalam 30 hari; status suspensi diturunkan secara dinamis dari tabel sanksi aktif.
13. **Penyisipan "Fase 5.5: Privacy Pack" sebagai Syarat Pilot-Lite:** Milestone *pilot-lite* diletakkan setelah Fase 5.5; seluruh dokumen privasi, consent GPS, job retensi, dan alur hapus akun wajib aktif sebelum pilot lapangan dimulai.
14. **Penyempurnaan Detail Teknis & Konsultasi Hukum:** Penanganan pembagian nol pada rumus float, penambahan status `PARTIALLY_REFUNDED`, aturan tombol penyelesaian penumpang saat `IN_PROGRESS`, pengembalian hak klarifikasi terlapor pada no-show, dan penambahan daftar pertanyaan konsultasi hukum fintech/UU PDP.

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
- **Biaya Layanan:** Dikenakan berbasis koin tertutup (1 koin Driver + 1 koin Passenger per perjalanan sukses). Nilai konseptual 1 koin = Rp500.
- **Bonus Pengguna Baru:** 30 koin bonus gratis, dikreditkan otomatis **hanya setelah verifikasi identitas kampus berhasil** dan dipastikan tidak memiliki catatan di tabel tombstone.
- **Jalur Verifikasi Kampus:**
  - **Jalur A (Primer - 100% Gratis):** Pemeriksaan klaim token Google (`email_verified == true` dan kecocokan domain email institusi dengan aturan *dot-boundary* whitelist).
  - **Jalur B (Sekunder / Cadangan):** Pengiriman kode OTP 6-digit ke email kampus via free tier provider (Resend/Brevo) dengan batas waktu 10 menit dan *rate limiting*.
  - *Catatan:* WhatsApp OTP tetap nonaktif secara default karena menimbulkan biaya per pesan.
- **Koin Tertutup (Closed-Loop Ledger):** Tabel buku besar keuangan bersifat *append-only* (tanpa `UPDATE`/`DELETE`). Semua jumlah uang dan koin dicatat sebagai bilangan bulat (*integer*).

---

## 2. Tabel Transisi Status Lengkap (Single Source of Truth)

Siklus hidup perjalanan dikendalikan oleh `ride_matches.status` sebagai *single source of truth*. Status pada `driver_ride` dan `passenger_ride` bergerak sinkron mengikuti perubahan pada match.

### A. Tabel Transisi `ride_matches` (Master Lifecycle)
| Status Asal | Status Tujuan | Pemicu (Trigger) | Efek ke Ledger | Dampak ke `driver_ride` & `passenger_ride` |
| :--- | :--- | :--- | :--- | :--- |
| *(None)* | `REQUESTED` | Driver mengirim ajakan tumpangan ke Passenger | Tidak ada | Status kedua ride tetap `OPEN` (tersembunyi dari pencarian lain) |
| `REQUESTED` | `EXPIRED` | Batas waktu respons `expires_at` terlewati | Tidak ada | Kedua ride kembali `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `REQUESTED` | `REJECTED` | Passenger menolak ajakan Driver | Tidak ada | Kedua ride kembali `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `REQUESTED` | `CANCELLED` *(Superseded)* | Match lain pada ride yang sama diterima (`MATCHED`) | Tidak ada (`cancel_reason = 'SUPERSEDED'`) | Ride mengikuti match yang diterima |
| `REQUESTED` | `MATCHED` | Passenger menerima ajakan (atomic lock & time-overlap check) | Tidak ada | Kedua ride berubah menjadi `MATCHED`. Seluruh match `REQUESTED` lain pada ride ini otomatis `CANCELLED` |
| `MATCHED` *(parsial)*| `MATCHED` | Salah satu pihak klik konfirmasi (saldo $\ge 1$) | Catat `HOLD_SERVICE_FEE` (-1) via `on_party_confirmed()` | Status ride tetap `MATCHED` |
| `MATCHED` | `CONFIRMED` | Pihak kedua klik konfirmasi (saldo $\ge 1$) | Catat `HOLD_SERVICE_FEE` (-1) via `on_party_confirmed()` | Status kedua ride tetap `MATCHED` (terkunci untuk jalan) |
| `MATCHED` | `CANCELLED` | Salah satu pihak batal sebelum konfirmasi lengkap | `RELEASE_HOLD` (+1) jika ada pihak yang sempat konfirmasi | Ride pembatal $\rightarrow$ `CANCELLED`; ride rekan $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `MATCHED` | `EXPIRED` *(Satu Pihak)* | Deadline konfirmasi lewat & hanya 1 pihak konfirmasi | `RELEASE_HOLD` (+1) pihak yang konfirmasi via `on_expired()` | Pihak tak konfirmasi $\rightarrow$ `CANCELLED`; pihak konfirmasi $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `MATCHED` | `EXPIRED` *(Nol Pihak)* | Deadline konfirmasi lewat & kedua pihak tak konfirmasi | Tidak ada hold | Kedua ride $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `CONFIRMED` | `IN_PROGRESS` | Driver klik *"Mulai Perjalanan"* setelah penumpang naik | Tidak ada | Status kedua ride tetap `MATCHED` |
| `IN_PROGRESS` | `COMPLETED` | (a) Passenger klik "Perjalanan OK" awal; ATAU (b) 60 mnt pasca Driver klik selesai; ATAU (c) ETA + 2 jam | Settle: `RELEASE_HOLD` (+1) lalu `SERVICE_FEE` (-1) via `on_completed()` | Status kedua ride menjadi `COMPLETED` |
| `IN_PROGRESS` | `DISPUTED` | Passenger mengajukan sanggahan dalam jendela 60 menit | Koin hold dibekukan | Status kedua ride tetap `MATCHED` |
| `DISPUTED` | `COMPLETED` | Admin memvalidasi perjalanan berhasil | Settle: `RELEASE_HOLD` (+1) lalu `SERVICE_FEE` (-1) | Status kedua ride menjadi `COMPLETED` |
| `DISPUTED` | `CANCELLED` | Admin batalkan ATAU timeout 72 jam tanpa keputusan admin | Eksekusi `RELEASE_HOLD` (+1) kedua belah pihak | Status kedua ride menjadi `CANCELLED` |
| `CONFIRMED` | `NO_SHOW_REPORTED` | Salah satu pihak lapor no-show pasca toleransi 10 mnt | Koin hold dibekukan | Status kedua ride tetap `MATCHED` |
| `NO_SHOW_REPORTED`| `NO_SHOW` | Laporan diverifikasi VALID oleh admin (maks. 72 jam) | Eksekusi `RELEASE_HOLD` (+1) kedua pihak; catat strike ke terlapor | Status kedua ride menjadi `CANCELLED` |
| `NO_SHOW_REPORTED`| `CANCELLED` | Laporan REJECTED oleh admin ATAU timeout 72 jam lewat | Eksekusi `RELEASE_HOLD` (+1) kedua pihak (tanpa sanksi) | Status kedua ride menjadi `CANCELLED` |
| `CONFIRMED` | `CANCELLED` *(Pra-Jalan)* | Pembatalan sah oleh salah satu pihak sebelum berangkat | Eksekusi `RELEASE_HOLD` (+1) kedua pihak; jika telat (<15 mnt), catat late cancel | Ride pembatal $\rightarrow$ `CANCELLED`; ride rekan $\rightarrow$ `OPEN` jika sisa waktu $\ge 30$ mnt, selain itu `EXPIRED` |
| `IN_PROGRESS` | `CANCELLED` *(Di Jalan)* | Pembatalan darurat di jalan (force majeure) | Eksekusi `RELEASE_HOLD` (+1) kedua pihak | Status KEDUA ride menjadi `CANCELLED` |

### B. Tabel Transisi `rides`
| Status Asal | Status Tujuan | Pemicu (Trigger) | Efek ke Ledger | Keterangan |
| :--- | :--- | :--- | :--- | :--- |
| *(None)* | `OPEN` | Pengguna mempublikasikan jadwal/rute | Tidak ada | Muncul di pencarian kandidat |
| `OPEN` | `MATCHED` | Salah satu tawaran diterima (`ride_matches` $\rightarrow$ `MATCHED`) | Tidak ada | Terkunci dalam proses perjalanan |
| `OPEN` | `EXPIRED` | Waktu keberangkatan lewat tanpa pasangan (`departure_time < NOW()`) | Tidak ada | Dijalankan oleh lazy check & sweeper |
| `MATCHED` | `OPEN` | Pasangan membatalkan / expired dan sisa waktu $\ge \text{REOPEN\_MIN\_LEAD\_MINUTES}$ | Tidak ada | Kembali aktif mencari pasangan baru |
| `MATCHED` | `EXPIRED` | Pasangan membatalkan / expired tetapi sisa waktu $< \text{REOPEN\_MIN\_LEAD\_MINUTES}$ | Tidak ada | Waktu terlalu mepet untuk dicocokkan ulang |
| `MATCHED` | `COMPLETED` | Match terkait mencapai status `COMPLETED` | Mengikuti match | Perjalanan tuntas |
| `MATCHED` | `CANCELLED` | Match dibatalkan oleh pengguna ini / kondisi darurat | Mengikuti match | Perjalanan batal |

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
│  ├── users, refresh_tokens, vehicles                   │
│  ├── deleted_user_tombstones, tombstone_identifiers    │
│  ├── rides (driver_ride & passenger_ride), sched_rides │
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
- **Fase 1b:** `deleted_user_tombstones`, `tombstone_identifiers`, `vehicles`, `coin_ledger` (beserta trigger Postgres anti-mutasi & partial index unik), `admin_audit_logs` (beserta trigger Postgres anti-mutasi).
- **Fase 2:** `rides`, `scheduled_rides`.
- **Fase 3:** `ride_matches` (dengan partial unique indexes, foreign key ganda, dan check constraint).
- **Fase 5:** `pickup_checkins`, `no_show_reports`, `sanctions`.
- **Fase 8:** `coin_packages`, `topup_orders`, `webhook_events`.

### Skema Tabel Database Lengkap (Semua Waktu Berbasis `TIMESTAMPTZ`)

1. **`users`:**
   - `id` (UUID, PK), `email` (VARCHAR, UNIQUE, nullable on delete), `phone_number` (VARCHAR, UNIQUE, nullable), `campus_email` (VARCHAR, UNIQUE, nullable), `full_name` (VARCHAR, nullable on delete), `campus_name` (VARCHAR, nullable on delete), `is_identity_verified` (BOOLEAN, default false), `deleted_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
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
   - `tombstone_identifiers`: `id` (UUID, PK), `tombstone_id` (UUID, FK), `identifier_type` (`EMAIL`, `PHONE`, `CAMPUS_EMAIL`), `identifier_hmac` (VARCHAR(64), UNIQUE - HMAC-SHA256).
   - *Aturan UPSERT Tombstone:* Jika pengguna menghapus akun dengan identitas yang sudah memiliki tombstone, record tombstone lama di-update: `expires_at` diperpanjang 1 tahun, `strike_dates_json` digabungkan, dan `sanction_ends_at` mengambil nilai terjauh.
   - *Normalisasi Identitas:* Identitas dibersihkan sebelum di-hash: email/campus_email di-*trim* dan di-*lowercase*; nomor HP dikonversi ke format standar E.164 (misal: `+628...`).
4. **`vehicles` (Fase 1b):**
   - `id` (UUID, PK), `user_id` (UUID, FK users), `vehicle_type` (VARCHAR, e.g. "Motor"), `vehicle_model` (VARCHAR, e.g. "Honda Vario Hitam"), `license_plate_masked` (VARCHAR, e.g. "*3821 AB"), `created_at` (TIMESTAMPTZ).
5. **`rides` (Fase 2):**
   - `id` (UUID, PK), `creator_id` (UUID, FK users), `scheduled_ride_id` (UUID, FK scheduled_rides, nullable), `role` (VARCHAR: `DRIVER`/`PASSENGER`), `origin_name` (VARCHAR), `origin_lat` (FLOAT), `origin_lon` (FLOAT), `dest_name` (VARCHAR), `dest_lat` (FLOAT), `dest_lon` (FLOAT), `departure_time` (TIMESTAMPTZ), `is_scheduled` (BOOLEAN), `cost_share_estimate` (INTEGER), `status` (VARCHAR: `OPEN`, `MATCHED`, `COMPLETED`, `CANCELLED`, `EXPIRED`), `created_at` (TIMESTAMPTZ).
6. **`scheduled_rides` (Fase 2):**
   - `id` (UUID, PK), `user_id` (UUID, FK users), `role` (VARCHAR), `days_of_week` (VARCHAR, e.g. "MON,TUE,WED,THU,FRI"), `departure_time_time` (TIME), `origin_lat` (FLOAT), `origin_lon` (FLOAT), `dest_lat` (FLOAT), `dest_lon` (FLOAT), `cost_share_estimate` (INTEGER), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
7. **`ride_matches` (Fase 3 - Master Lifecycle):**
   - `id` (UUID, PK), `driver_ride_id` (UUID, FK rides), `passenger_ride_id` (UUID, FK rides), `driver_id` (UUID, FK users), `passenger_id` (UUID, FK users), `status` (VARCHAR: `REQUESTED`, `MATCHED`, `CONFIRMED`, `IN_PROGRESS`, `COMPLETED`, `DISPUTED`, `NO_SHOW_REPORTED`, `NO_SHOW`, `CANCELLED`, `EXPIRED`), `driver_confirmed_at` (TIMESTAMPTZ, nullable), `passenger_confirmed_at` (TIMESTAMPTZ, nullable), `driver_completed_at` (TIMESTAMPTZ, nullable), `passenger_completed_at` (TIMESTAMPTZ, nullable), `estimated_arrival_at` (TIMESTAMPTZ, nullable), `cancelled_by` (UUID, FK users, nullable), `cancelled_at` (TIMESTAMPTZ, nullable), `cancel_reason` (TEXT, nullable), `is_late_cancel` (BOOLEAN, default false), `dispute_reason` (TEXT, nullable), `dispute_deadline` (TIMESTAMPTZ, nullable - 72 jam), `expires_at` (TIMESTAMPTZ), `confirmation_deadline` (TIMESTAMPTZ), `created_at` (TIMESTAMPTZ).
   - *Integritas & Constraint Database:*
     ```sql
     ALTER TABLE ride_matches ADD CONSTRAINT chk_driver_passenger_distinct CHECK (driver_id <> passenger_id);

     CREATE UNIQUE INDEX uq_active_passenger_ride ON ride_matches (passenger_ride_id)
     WHERE status IN ('MATCHED', 'CONFIRMED', 'IN_PROGRESS', 'DISPUTED', 'NO_SHOW_REPORTED');

     CREATE UNIQUE INDEX uq_active_driver_ride ON ride_matches (driver_ride_id)
     WHERE status IN ('MATCHED', 'CONFIRMED', 'IN_PROGRESS', 'DISPUTED', 'NO_SHOW_REPORTED');
     ```
   - *Validasi Service Layer:* Backend memvalidasi mutlak: `driver_ride.role == 'DRIVER'`, `passenger_ride.role == 'PASSENGER'`, `driver_id == driver_ride.creator_id`, dan `passenger_id == passenger_ride.creator_id`.
8. **`pickup_checkins` (Fase 5):**
   - `id` (UUID, PK), `match_id` (UUID, FK ride_matches), `user_id` (UUID, FK users), `lat` (FLOAT, nullable on purge), `lon` (FLOAT, nullable on purge), `distance_to_pickup_m` (FLOAT - bukti permanen), `checked_in_at` (TIMESTAMPTZ - bukti permanen), `purge_after` (TIMESTAMPTZ - default `checked_in_at + INTERVAL '7 days'`).
9. **`no_show_reports` (Fase 5):**
   - `id` (UUID, PK), `match_id` (UUID, FK ride_matches), `reporter_id` (UUID, FK users), `reported_id` (UUID, FK users), `distance_meters` (FLOAT), `time_diff_seconds` (INTEGER), `reporter_lat` (FLOAT, nullable on purge), `reporter_lon` (FLOAT, nullable on purge), `status` (VARCHAR: `PENDING_REVIEW`, `VALIDATED`, `REJECTED`, `EXPIRED_AUTO_RELEASE`), `reporter_notes` (TEXT), `reported_clarification` (TEXT, nullable - hak klarifikasi terlapor), `admin_notes` (TEXT, nullable), `admin_id` (UUID, FK users, nullable), `review_deadline` (TIMESTAMPTZ - 72 jam), `purge_after` (TIMESTAMPTZ - default `review_deadline + INTERVAL '7 days'`), `resolved_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
   - *Constraint 1 Laporan Terbuka:*
     ```sql
     CREATE UNIQUE INDEX uq_one_pending_no_show_per_match ON no_show_reports (match_id)
     WHERE status = 'PENDING_REVIEW';
     ```
10. **`sanctions` (Fase 5):**
    - `id` (UUID, PK), `user_id` (UUID, FK users), `sanction_type` (VARCHAR: `WARNING`, `MATCHING_RESTRICTION_24H`, `SUSPEND_24H`, `SUSPEND_7D`, `ACCOUNT_REVIEW`), `reason` (TEXT), `starts_at` (TIMESTAMPTZ), `ends_at` (TIMESTAMPTZ), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
    - Status suspensi/restriksi pengguna diturunkan langsung dari query baris sanksi aktif (`WHERE user_id = :uid AND is_active = true AND ends_at > NOW()`).
11. **`admin_audit_logs` (Fase 1b - Append-Only dengan Trigger Anti-Mutasi):**
    - `id` (UUID, PK), `admin_user_id` (UUID, FK users), `admin_email` (VARCHAR - snapshot email saat aksi), `action_type` (VARCHAR: `ADMIN_ADJUSTMENT`, `RESOLVE_DISPUTE`, `VALIDATE_NO_SHOW`, `REJECT_NO_SHOW`, `MANUAL_REFUND`), `target_user_id` (UUID, nullable), `reference_id` (UUID, nullable), `reason` (TEXT), `ip_address` (VARCHAR), `created_at` (TIMESTAMPTZ).
    - *Trigger Mutasi:* `trg_prevent_admin_audit_logs_mutation` menolak keras `UPDATE` dan `DELETE`.
12. **`coin_ledger` (Fase 1b - Append-Only dengan Trigger Anti-Mutasi & Anti-Hold Ganda):**
    - `id` (UUID, PK), `user_id` (UUID, FK users), `transaction_type` (VARCHAR: `BONUS`, `TOPUP_PAID`, `HOLD_SERVICE_FEE`, `RELEASE_HOLD`, `SERVICE_FEE`, `REFUND`, `ADMIN_ADJUSTMENT`), `amount` (INTEGER, positif/negatif), `coin_category` (VARCHAR: `BONUS`, `PAID`), `reference_id` (UUID), `reference_type` (VARCHAR: `RIDE_MATCH`, `TOPUP_ORDER`, `ADMIN_ACTION`, `SIGNUP_REWARD`), `idempotency_key` (VARCHAR, UNIQUE), `created_at` (TIMESTAMPTZ), `actor` (VARCHAR).
    - *Index Unik Parsial Pencegah Hold Ganda:*
      ```sql
      CREATE UNIQUE INDEX uq_coin_ledger_hold_prevent 
      ON coin_ledger (reference_type, reference_id, user_id, transaction_type) 
      WHERE transaction_type IN ('HOLD_SERVICE_FEE', 'RELEASE_HOLD', 'SERVICE_FEE');
      ```
    - *Trigger Mutasi:* `trg_prevent_coin_ledger_mutation` menolak keras `UPDATE` dan `DELETE`.
13. **`coin_packages` & `topup_orders` (Fase 8):**
    - `coin_packages`: `id` (UUID, PK), `package_code` (VARCHAR, UNIQUE), `coin_amount` (INTEGER), `price_idr` (INTEGER), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
    - `topup_orders`: `id` (UUID, PK), `order_number` (VARCHAR, UNIQUE), `user_id` (UUID, FK users), `package_id` (UUID, FK coin_packages), `amount_idr` (INTEGER), `paid_amount_idr` (INTEGER, nullable), `refunded_amount_idr` (INTEGER, default 0), `coins_to_credit` (INTEGER), `status` (VARCHAR: `PENDING`, `PAID`, `EXPIRED`, `FAILED`, `REFUNDED`, `REFUND_REQUIRED`, `REVIEW_REQUIRED`, `PARTIALLY_REFUNDED`), `payment_link` (TEXT, nullable), `gateway_reference` (VARCHAR, nullable), `expires_at` (TIMESTAMPTZ), `paid_at` (TIMESTAMPTZ, nullable), `created_at` (TIMESTAMPTZ).
14. **`webhook_events` & `system_configurations`:**
    - `webhook_events`: `id` (UUID, PK), `gateway_name` (VARCHAR), `event_id` (VARCHAR), `order_number` (VARCHAR), `signature` (VARCHAR), `payload_json` (JSONB, nullable on purge), `processed_at` (TIMESTAMPTZ), `status` (VARCHAR: `PROCESSED`, `IGNORED`, `FAILED`), `expires_at` (TIMESTAMPTZ - retensi 90 hari). Constraint: `UNIQUE(gateway_name, event_id)`.
    - `system_configurations`: `key` (VARCHAR, PK), `value` (VARCHAR), `description` (TEXT), `updated_at` (TIMESTAMPTZ). Nilai konfigurasi: `MAX_TOPUP_PER_TX_IDR=100000`, `MAX_USER_BALANCE_COINS=200`, `INITIAL_BONUS_COINS=30`, `ALLOWED_CAMPUS_DOMAINS=ui.ac.id,ugm.ac.id,itb.ac.id`, `MATCH_OVERLAP_MINUTES=90`, `REOPEN_MIN_LEAD_MINUTES=30`.
    - *Aturan Mutlak:* `TOPUP_ENABLED`, `PAYMENT_ENV`, `ADMIN_EMAILS`, dan `TOMBSTONE_HMAC_SECRET` dilarang disimpan di tabel database; murni dibaca dari Environment Variable sistem (`.env`).

---

## 4. Tabel Tugas Pembersih Berkala (*Background Sweeper Tasks*)

Hosting gratis dapat tidur (*sleep*), sehingga seluruh tugas dirancang **idempotent, catch-up safe, dan dieksekusi secara lazy saat request tiba**, didukung oleh pemanggilan cron eksternal gratis (cron-job.org / GitHub Actions) pada endpoint internal `POST /internal/sweeper/run` yang diamankan header `X-Internal-Cron-Secret`.

| No | Nama Tugas | Kondisi Pemicu (Trigger) | Aksi Database (Action) | Catatan Idempotensi & Keamanan |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Match REQUESTED Expiry** | `ride_matches.status = 'REQUESTED' AND expires_at < NOW()` | Update match $\rightarrow$ `EXPIRED`. Cek sisa waktu ride ke `departure_time`: jika $\ge 30$ mnt $\rightarrow$ ride `OPEN`, selain itu `EXPIRED`. | Klausa `FOR UPDATE SKIP LOCKED`. Idempotent (status terminal `EXPIRED`). |
| 2 | **Confirmation Deadline Expiry** | `ride_matches.status = 'MATCHED' AND confirmation_deadline < NOW()` | Update match $\rightarrow$ `EXPIRED`. Panggil `on_expired()`: jika ada pihak sempat konfirmasi, catat `RELEASE_HOLD` (+1). Cek sisa waktu: jika $\ge 30$ mnt $\rightarrow$ ride `OPEN`, selain itu `EXPIRED`. | Menggunakan `idempotency_key` release hold. Aman dijalankan berulang. |
| 3 | **IN_PROGRESS Auto-Complete** | `ride_matches.status = 'IN_PROGRESS' AND ((driver_completed_at IS NOT NULL AND driver_completed_at + INTERVAL '60 min' < NOW()) OR (estimated_arrival_at + INTERVAL '2 hours' < NOW()))` | Update match $\rightarrow$ `COMPLETED`. Panggil `on_completed()`: eksekusi `RELEASE_HOLD` (+1) lalu `SERVICE_FEE` (-1) per pihak. Update status kedua ride $\rightarrow$ `COMPLETED`. | Ditransaksikan atomik per match; dicegah jika ada sanggahan terbuka. |
| 4 | **DISPUTED 72h Auto-Release** | `ride_matches.status = 'DISPUTED' AND dispute_deadline < NOW()` | Update match $\rightarrow$ `CANCELLED`. Eksekusi `RELEASE_HOLD` (+1) kedua pihak tanpa fee. Update kedua ride $\rightarrow$ `CANCELLED`. | Batas waktu 72 jam pasti. Mencegah koin pengguna tertahan selamanya. |
| 5 | **NO_SHOW_REPORTED 72h Auto-Release** | `ride_matches.status = 'NO_SHOW_REPORTED' AND review_deadline < NOW()` | Update match $\rightarrow$ `CANCELLED`, laporan $\rightarrow$ `EXPIRED_AUTO_RELEASE`. Eksekusi `RELEASE_HOLD` (+1) kedua pihak (tanpa sanksi). Update ride $\rightarrow$ `CANCELLED`. | Melindungi hak pengguna jika admin lalai meninjau laporan no-show. |
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
- **Database:** Setup PostgreSQL ringan + migrasi tabel `users`, `refresh_tokens`, dan `system_configurations`.
- **Fitur:** Login Google OAuth dengan verifikasi token JWT (`email_verified == true`), pencocokan domain kampus dot-boundary (`domain == allowed || domain.endswith("." + allowed)`), helper `is_admin_email()` via `ADMIN_EMAILS`, manajemen sesi rotasi refresh token dengan deteksi reuse token family, dan rate limiting pada endpoint auth.
- **Pengujian:** Verifikasi token JWT, uji reuse detection refresh token (seluruh family dicabut), uji rate limiter, dan uji dot-boundary whitelist.

### Fase 1b: Verifikasi Identitas, Kendaraan, Bonus Awal, & Immutability Ledger
- **Fokus:** Pengikatan identitas kampus, inisialisasi ledger keuangan, dan log audit admin.
- **Database:** Migrasi tabel `deleted_user_tombstones`, `tombstone_identifiers`, `vehicles`, `coin_ledger`, dan `admin_audit_logs`. Pemasangan trigger Postgres anti-mutasi `trg_prevent_coin_ledger_mutation` dan `trg_prevent_admin_audit_logs_mutation`, serta index unik `uq_coin_ledger_hold_prevent`.
- **Fitur:** Verifikasi email kampus Jalur A (Google ID Token) dan Jalur B (One-time code email jika kampus non-Google). Pencatatan 30 koin bonus awal via `coin_ledger` dengan verifikasi bebas sanksi di tabel tombstone HMAC-SHA256 (dengan aturan UPSERT). Input kendaraan dengan plat nomor tersamar (`*3821 AB`).
- **Pengujian:** Uji trigger Postgres menolak `UPDATE`/`DELETE` pada ledger dan log audit admin, uji indeks unik anti-hold ganda, dan uji tombstone HMAC-SHA256 mencegah klaim bonus ganda pasca hapus akun.

### Fase 2: Manajemen Perjalanan & Koordinat Rute
- **Fokus:** Pembuatan rute tumpangan *on-demand* dan pola jadwal rutin (Senin–Jumat).
- **Database:** Migrasi tabel `rides` (termasuk `scheduled_ride_id`) dan `scheduled_rides`.
- **Fitur:** Input asal, tujuan, waktu, estimasi biaya bersama. Peta OpenStreetMap (flutter_map).
- **Pengujian:** Validasi input koordinat, query filter perjalanan aktif, kalkulasi jarak rute Haversine/OSRM.

### Fase 3: Matching Engine, Dynamic Lazy Timeout, & Time-Overlap Check
- **Fokus:** Algoritma scoring (Rute 35%, Jarak Jemput 25%, Waktu 25%, Biaya 15%).
- **Database:** Migrasi tabel `ride_matches` (dengan partial unique indexes, constraint `driver_id <> passenger_id`, dan foreign key ganda).
- **Fitur:** Pemilihan Passenger oleh Driver dengan penguncian atomik `SELECT ... FOR UPDATE`. Penerimaan ajakan perjalanan otomatis membatalkan tawaran `REQUESTED` lain (`SUPERSEDED`) dan menolak jika pengguna memiliki match aktif yang bertabrakan waktu (`MATCH_OVERLAP_MINUTES`).
- **Pengujian:** Bobot scoring, uji balapan dua driver memilih passenger yang sama (verifikasi partial index), uji penolakan time-overlap match, dan uji pembatalan otomatis match tersaingi (*superseded*).

### Fase 4: Siklus Status Perjalanan & Lifecycle Hooks
- **Fokus:** State machine transisi lengkap `ride_matches` dan `rides`.
- **Fitur:**
  - Lifecycle hooks: `on_party_confirmed(user_id)`, `on_expired()`, `on_no_show()`, `on_completed()`, dan `on_cancelled()` (awalnya no-op).
  - Pemicu tunggal `IN_PROGRESS` saat Driver menekan tombol "Mulai Perjalanan".
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

## 7. Pertanyaan untuk Konsultasi Hukum (Legal Compliance Checklist)

Sebelum melangkah ke aktivasi produksi (`PAYMENT_ENV=production`), daftar pertanyaan berikut wajib dikonsultasikan kepada konsultan hukum fintech & privasi data independen:
1. **UU Pelindungan Data Pribadi (UU PDP):** Apakah penyimpanan riwayat hash identitas (`tombstone_identifiers` via HMAC-SHA256) selama 1 tahun pasca penghapusan akun memenuhi ketentuan *pseudonymization* yang sah untuk tujuan pencegahan fraud/sanksi, dan bagaimana status penautan `user_uuid_history` terhadap riwayat ledger anonim?
2. **Ketentuan Uang Elektronik Closed-Loop Bank Indonesia (Pasca 31 Maret 2026):** Berdasarkan pembaruan regulasi sistem pembayaran Bank Indonesia, apakah model koin tertutup Ajun murni berstatus *closed-loop* non-PJP, berapa batas pasti akumulasi dana float yang mewajibkan pelaporan berkala ke BI, dan apakah dana float wajib ditempatkan pada rekening *escrow* terpisah?
3. **Kebijakan Pembayaran Toko Aplikasi (Google Play Store & Apple App Store):** Apakah penjualan koin biaya layanan pencocokan tumpangan fisik antarmahasiswa dikategorikan sebagai *in-app digital goods* yang wajib menggunakan Google Play Billing (komisi 15–30%), atau dapat dikecualikan sebagai *facilitation of real-world physical services* sehingga legal menggunakan payment gateway pihak ketiga (Midtrans/Xendit)?
4. **Syarat & Ketentuan Merchant Payment Gateway:** Apakah badan usaha/organisasi mahasiswa pengelola Ajun memenuhi syarat kepatuhan *Know Your Business* (KYB) merchant gateway untuk kategori platform agregator/matching komunitas?

---

## 8. Hasil Pemeriksaan Konsistensi (Self-Consistency Cross-Check)

Berikut adalah rekapitulasi audit konsistensi internal yang dilakukan terhadap dokumen v1.7:
1. **Pemeriksaan Kolom & Relasi:**
   - `ride_matches` kini secara konsisten menggunakan `driver_ride_id` dan `passenger_ride_id` (menggantikan `ride_id` tunggal yang usang).
   - Seluruh tabel relasional telah dilengkapi foreign key dan indeks penunjang (`scheduled_ride_id` pada `rides`, `admin_user_id` pada `admin_audit_logs`).
2. **Pemeriksaan Status & Enum:**
   - Status `rides` konsisten 5 nilai: `OPEN`, `MATCHED`, `COMPLETED`, `CANCELLED`, `EXPIRED`.
   - Status `ride_matches` mencakup seluruh alur termasuk `SUPERSEDED`, `DISPUTED`, dan `NO_SHOW_REPORTED`.
   - Status `topup_orders` mencakup `REVIEW_REQUIRED` dan `PARTIALLY_REFUNDED`.
3. **Penyelarasan Tipe Waktu:**
   - 100% kolom waktu di seluruh tabel database telah diubah dari `TIMESTAMP` biasa menjadi `TIMESTAMPTZ` (UTC) demi mencegah anomali zona waktu lintas perangkat mahasiswa.
4. **Konsistensi Variabel Lingkungan (*Environment Variables*):**
   - Dipastikan tidak ada flag sensitif yang disimpan di database: `TOPUP_ENABLED`, `PAYMENT_ENV`, `ADMIN_EMAILS`, dan `TOMBSTONE_HMAC_SECRET` ditegaskan murni berasal dari environment variable sistem hosting.
5. **Pencegahan Kontradiksi yang Diperbaiki:**
   - Diperbaiki kontradiksi seputar tindakan ketika kedua pihak gagal konfirmasi: kini diputuskan secara seragam mengikuti aturan lead time `REOPEN_MIN_LEAD_MINUTES` (jika $\ge 30$ mnt $\rightarrow$ `OPEN`, selain itu `EXPIRED`).
   - Diperbaiki potensi division-by-zero pada formula float koin berbayar saat sistem pertama kali dijalankan tanpa ada order `PAID`.
   - Diperbaiki potensi kegagalan relasional tombstone pada penghapusan akun berulang melalui mekanisme `UPSERT`.
