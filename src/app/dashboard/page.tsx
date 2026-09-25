"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type AjunUser = {
  id: string;
  username: string;
  email: string;
  coinBalance: number;
  referralCode: string;
  qrToken: string;
};

type Trip = {
  id: string;
  driverId: string;
  passengerId: string | null;
  destination: string;
  status: string;
  driver: {
    id: string;
    username: string;
    email: string;
  };
  passenger?: {
    id: string;
    username: string;
    email: string;
  } | null;
};

export default function DashboardPage() {
  const router = useRouter();

  const [user, setUser] = useState<AjunUser | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [myTrips, setMyTrips] = useState<Trip[]>([]);
const [loadingMyTrips, setLoadingMyTrips] = useState(false);
  const [loadingTrips, setLoadingTrips] = useState(false);
  const [selectingTripId, setSelectingTripId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [actionTripId, setActionTripId] = useState<string | null>(null);

  useEffect(() => {
    const storedUser = sessionStorage.getItem("ajun_user");

    if (!storedUser) {
      router.replace("/login");
      return;
    }

    try {
      setUser(JSON.parse(storedUser));
    } catch {
      sessionStorage.removeItem("ajun_user");
      router.replace("/login");
    }
  }, [router]);

  useEffect(() => {
  if (!user) return;

  const currentUser = user;

  async function loadTrips() {
      setLoadingTrips(true);
      setMessage("");

      try {
        const response = await fetch("/api/trips", {
          method: "GET",
          cache: "no-store",
        });

        const data = await response.json();

        if (!response.ok) {
          setMessage(data.message || "Gagal mengambil pesanan.");
          return;
        }

        setTrips(data.trips || []);
        const myTripsResponse = await fetch(
  `/api/trips/my?userId=${currentUser.id}`,
  {
    method: "GET",
    cache: "no-store",
  }
);

const myTripsData = await myTripsResponse.json();

if (myTripsResponse.ok) {
  setMyTrips(myTripsData.trips || []);
}
      } catch (error) {
        console.error(error);
        setMessage("Tidak dapat mengambil pesanan AJUN.");
      } finally {
        setLoadingTrips(false);
      }
    }

    loadTrips();
  }, [user]);

  async function handleSelectTrip(tripId: string) {
    if (!user) return;

    setSelectingTripId(tripId);
    setMessage("");

    try {
      const response = await fetch("/api/trips/select", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          tripId,
          passengerId: user.id,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        setMessage(data.message || "Gagal memilih pesanan.");
        return;
      }

      setMessage("Pesanan berhasil dipilih.");

      setTrips((currentTrips) =>
        currentTrips.filter((trip) => trip.id !== tripId)
      );
    } catch (error) {
      console.error(error);
      setMessage("Tidak dapat terhubung ke server AJUN.");
    } finally {
      setSelectingTripId(null);
    }
  }
async function handleTripAction(
  tripId: string,
  endpoint: string,
  body: Record<string, string> = {}
) {
  if (!user) return;

  setActionTripId(tripId);
  setMessage("");

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tripId,
        ...body,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      setMessage(data.message || "Aksi perjalanan gagal.");
      return;
    }

    setMessage(data.message || "Aksi perjalanan berhasil.");

    const myTripsResponse = await fetch(
      `/api/trips/my?userId=${user.id}`,
      {
        method: "GET",
        cache: "no-store",
      }
    );

    const myTripsData = await myTripsResponse.json();

    if (myTripsResponse.ok) {
      setMyTrips(myTripsData.trips || []);
    }

    if (data.trip) {
      setTrips((currentTrips) =>
        currentTrips.filter((trip) => trip.id !== tripId)
      );
    }
  } catch (error) {
    console.error(error);
    setMessage("Tidak dapat terhubung ke server AJUN.");
  } finally {
    setActionTripId(null);
  }
}
  function handleLogout() {
    sessionStorage.removeItem("ajun_user");
    router.replace("/login");
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-white">
        <p className="text-slate-400">Memuat AJUN...</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400">
              Antar Jemput UNDIP
            </p>

            <h1 className="mt-1 text-3xl font-bold">
              Dashboard AJUN
            </h1>
          </div>

          <button
            onClick={handleLogout}
            className="rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/10"
          >
            Keluar
          </button>
        </header>

        <section className="grid gap-5 md:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
            <p className="text-sm text-slate-400">
              Akun AJUN
            </p>

            <h2 className="mt-2 text-2xl font-bold">
              {user.username}
            </h2>

            <p className="mt-1 text-sm text-slate-400">
              {user.email}
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
            <p className="text-sm text-slate-400">
              Saldo Koin AJUN
            </p>

            <p className="mt-2 text-4xl font-bold">
              {user.coinBalance}
            </p>

            <p className="mt-2 text-sm text-slate-500">
              1 koin = Rp500
            </p>
          </div>
        </section>

        <section className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-6">
          <h2 className="text-xl font-semibold">
            Pesanan Tersedia
          </h2>

          <p className="mt-1 text-sm text-slate-400">
            Pilih pesanan antar yang tersedia.
          </p>

          {message && (
            <div className="mt-4 rounded-xl border border-white/10 bg-slate-900 p-3 text-sm text-slate-300">
              {message}
            </div>
          )}

          {loadingTrips ? (
            <p className="mt-5 text-sm text-slate-400">
              Memuat pesanan...
            </p>
          ) : trips.length === 0 ? (
            <p className="mt-5 text-sm text-slate-500">
              Belum ada pesanan tersedia.
            </p>
          ) : (
            <div className="mt-5 space-y-4">
              {trips.map((trip) => {
                const isOwnTrip = trip.driverId === user.id;

                return (
                  <div
                    key={trip.id}
                    className="rounded-2xl border border-white/10 bg-slate-900 p-5"
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-xs text-slate-500">
                          Tujuan
                        </p>

                        <h3 className="mt-1 text-lg font-semibold">
                          {trip.destination}
                        </h3>

                        <p className="mt-2 text-sm text-slate-400">
                          Driver:{" "}
                          <span className="text-white">
                            {trip.driver.username}
                          </span>
                        </p>

                        <p className="mt-1 text-xs text-slate-500">
                          Status: {trip.status}
                        </p>
                      </div>

                      <button
                        onClick={() => handleSelectTrip(trip.id)}
                        disabled={isOwnTrip || selectingTripId === trip.id}
                        className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
                      >
                        {isOwnTrip
                          ? "Pesanan Saya"
                          : selectingTripId === trip.id
                            ? "Memilih..."
                            : "Pilih Pesanan"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
<section className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-6">
  <h2 className="text-xl font-semibold">
    Pesanan Saya
  </h2>

  <p className="mt-1 text-sm text-slate-400">
    Pesanan yang kamu buat atau kamu pilih.
  </p>

  {myTrips.length === 0 ? (
    <p className="mt-5 text-sm text-slate-500">
      Belum ada pesanan.
    </p>
  ) : (
    <div className="mt-5 space-y-4">
      {myTrips.map((trip) => (
        <div
          key={trip.id}
          className="rounded-2xl border border-white/10 bg-slate-900 p-5"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs text-slate-500">
                Tujuan
              </p>

              <h3 className="mt-1 text-lg font-semibold">
                {trip.destination}
              </h3>

              <p className="mt-2 text-sm text-slate-400">
                Driver:{" "}
                <span className="text-white">
                  {trip.driver?.username ?? "-"}
                </span>
              </p>

              <p className="mt-1 text-sm text-slate-400">
                Penumpang:{" "}
                <span className="text-white">
                  {trip.passenger?.username ?? "-"}
                </span>
              </p>
            </div>

            <div className="rounded-xl border border-white/10 px-4 py-2 text-center">
              <p className="text-xs text-slate-500">
                Status
              </p>

              <p className="mt-1 font-semibold">
  {trip.status === "AVAILABLE"
    ? "Tersedia"
    : trip.status === "SELECTED"
      ? "Dipilih Penumpang"
      : trip.status === "WAITING_CONFIRMATION"
        ? "Menunggu Konfirmasi Driver"
        : trip.status === "MATCHED"
          ? "Penumpang Dikonfirmasi"
          : trip.status === "LOCKED"
            ? "Koin Terkunci"
            : trip.status === "VERIFIED"
              ? "Terverifikasi"
              : trip.status === "ON_TRIP"
                ? "Sedang Berjalan"
                : trip.status === "COMPLETED"
                  ? "Selesai"
                  : trip.status}
</p>
            </div>
            {trip.status === "WAITING_CONFIRMATION" &&
  trip.driverId === user.id && (
    <button
      onClick={() =>
        handleTripAction(
          trip.id,
          "/api/trips/confirm",
          {
            driverId: user.id,
          }
        )
      }
      disabled={actionTripId === trip.id}
      className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
    >
      {actionTripId === trip.id
        ? "Mengonfirmasi..."
        : "Konfirmasi Penumpang"}
    </button>
  )}
  {trip.status === "MATCHED" &&
  trip.driverId === user.id && (
  <button
    onClick={() =>
      handleTripAction(
        trip.id,
        "/api/trips/lock"
      )
    }
    disabled={actionTripId === trip.id}
    className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
  >
    {actionTripId === trip.id
      ? "Mengunci Koin..."
      : "Kunci Koin"}
  </button>
)}

{trip.status === "LOCKED" &&
  trip.passengerId === user.id && (
  <button
    onClick={() =>
      handleTripAction(
        trip.id,
        "/api/trips/verify",
        {
          qrToken: user.qrToken,
        }
      )
    }
    disabled={actionTripId === trip.id}
    className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
  >
    {actionTripId === trip.id
      ? "Memverifikasi..."
      : "Verifikasi QR"}
  </button>
)}

{trip.status === "VERIFIED" &&
  trip.driverId === user.id && (
  <button
    onClick={() =>
      handleTripAction(
        trip.id,
        "/api/trips/start"
      )
    }
    disabled={actionTripId === trip.id}
    className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
  >
    {actionTripId === trip.id
      ? "Memulai..."
      : "Mulai Perjalanan"}
  </button>
)}
{trip.status === "ON_TRIP" &&
  trip.driverId === user.id && (
  <button
    onClick={() =>
      handleTripAction(
        trip.id,
        "/api/trips/complete"
      )
    }
    disabled={actionTripId === trip.id}
    className="rounded-xl bg-white px-5 py-3 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
  >
    {actionTripId === trip.id
      ? "Menyelesaikan..."
      : "Selesaikan Perjalanan"}
  </button>
)}
          </div>
        </div>
      ))}
    </div>
  )}
</section>
        <section className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-6">
          <h2 className="text-xl font-semibold">
            Identitas AJUN
          </h2>

          <div className="mt-4 space-y-3">
            <div>
              <p className="text-xs text-slate-500">
                Referral Code
              </p>

              <p className="font-mono text-sm">
                {user.referralCode}
              </p>
            </div>

            <div>
              <p className="text-xs text-slate-500">
                QR Token
              </p>

              <p className="break-all font-mono text-sm text-slate-300">
                {user.qrToken}
              </p>
            </div>
          </div>
        </section>

        <section className="mt-5">
          <button
            disabled={user.coinBalance < 1}
            className="w-full rounded-2xl bg-white px-6 py-4 font-semibold text-slate-950 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            {user.coinBalance >= 1
              ? "Mulai Perjalanan"
              : "Minimal 1 Koin untuk Perjalanan"}
          </button>
        </section>
      </div>
    </main>
  );
}