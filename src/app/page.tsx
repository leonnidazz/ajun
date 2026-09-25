export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <section className="mx-auto flex min-h-screen max-w-6xl flex-col items-center justify-center px-6 text-center">
        <div className="mb-6 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
          Antar Jemput UNDIP
        </div>

        <h1 className="text-6xl font-bold tracking-tight">
          AJUN
        </h1>

        <p className="mt-4 max-w-2xl text-lg text-slate-300">
          Platform antar jemput yang mempertemukan mahasiswa
          dengan pengendara yang memiliki tujuan searah.
        </p>

        <div className="mt-10 flex gap-4">
          <button className="rounded-xl bg-white px-6 py-3 font-semibold text-slate-950 transition hover:bg-slate-200">
            Masuk
          </button>

          <button className="rounded-xl border border-white/20 px-6 py-3 font-semibold transition hover:bg-white/10">
            Daftar
          </button>
        </div>

        <div className="mt-16 grid w-full max-w-4xl gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
            <h2 className="font-semibold">A — Driver</h2>
            <p className="mt-2 text-sm text-slate-400">
              Membawa penumpang yang memiliki arah perjalanan yang sesuai.
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
            <h2 className="font-semibold">B — Penumpang</h2>
            <p className="mt-2 text-sm text-slate-400">
              Menemukan driver yang memiliki perjalanan searah.
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
            <h2 className="font-semibold">Koin AJUN</h2>
            <p className="mt-2 text-sm text-slate-400">
              1 Koin AJUN = Rp500.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}