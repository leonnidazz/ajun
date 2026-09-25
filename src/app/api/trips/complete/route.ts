import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const tripId = String(body.tripId ?? "").trim();

    if (!tripId) {
      return NextResponse.json(
        {
          success: false,
          message: "tripId wajib diisi.",
        },
        { status: 400 }
      );
    }

    const result = await prisma.$transaction(async (tx) => {
      const trip = await tx.trip.findUnique({
        where: {
          id: tripId,
        },
      });

      if (!trip) {
        throw new Error("TRIP_NOT_FOUND");
      }

      if (trip.status !== "ON_TRIP") {
        throw new Error("TRIP_NOT_ON_TRIP");
      }

      if (!trip.driverId || !trip.passengerId) {
        throw new Error("USER_NOT_COMPLETE");
      }

      if (!trip.driverCoinLocked || !trip.passengerCoinLocked) {
        throw new Error("COIN_NOT_LOCKED");
      }

      const driver = await tx.user.findUnique({
        where: {
          id: trip.driverId,
        },
      });

      const passenger = await tx.user.findUnique({
        where: {
          id: trip.passengerId,
        },
      });

      if (!driver || !passenger) {
        throw new Error("USER_NOT_FOUND");
      }

      if (driver.lockedCoins < 1) {
        throw new Error("DRIVER_LOCKED_COIN_INVALID");
      }

      if (passenger.lockedCoins < 1) {
        throw new Error("PASSENGER_LOCKED_COIN_INVALID");
      }

      /*
       * Untuk tahap testing ini:
       * - 1 koin driver dikembalikan ke saldo driver
       * - 1 koin passenger dikembalikan ke saldo passenger
       * - lockedCoins masing-masing dikurangi 1
       *
       * Nanti mekanisme settlement bisa kita ubah
       * sesuai aturan bisnis AJUN.
       */

      const updatedDriver = await tx.user.update({
        where: {
          id: driver.id,
        },
        data: {
          coinBalance: {
            increment: 1,
          },
          lockedCoins: {
            decrement: 1,
          },
        },
        select: {
          id: true,
          username: true,
          coinBalance: true,
          lockedCoins: true,
        },
      });

      const updatedPassenger = await tx.user.update({
        where: {
          id: passenger.id,
        },
        data: {
          coinBalance: {
            increment: 1,
          },
          lockedCoins: {
            decrement: 1,
          },
        },
        select: {
          id: true,
          username: true,
          coinBalance: true,
          lockedCoins: true,
        },
      });

      const updatedTrip = await tx.trip.update({
        where: {
          id: trip.id,
        },
        data: {
          status: "COMPLETED",
          driverCoinLocked: false,
          passengerCoinLocked: false,
        },
        include: {
          driver: {
            select: {
              id: true,
              username: true,
              email: true,
            },
          },
          passenger: {
            select: {
              id: true,
              username: true,
              email: true,
            },
          },
        },
      });

      return {
        trip: updatedTrip,
        driver: updatedDriver,
        passenger: updatedPassenger,
      };
    });

    return NextResponse.json({
      success: true,
      message: "Perjalanan berhasil diselesaikan.",
      trip: result.trip,
      driver: result.driver,
      passenger: result.passenger,
    });
  } catch (error) {
    console.error("COMPLETE_TRIP_ERROR:", error);

    const errorMessage =
      error instanceof Error ? error.message : "UNKNOWN_ERROR";

    if (errorMessage === "TRIP_NOT_FOUND") {
      return NextResponse.json(
        {
          success: false,
          message: "Pesanan tidak ditemukan.",
        },
        { status: 404 }
      );
    }

    if (errorMessage === "TRIP_NOT_ON_TRIP") {
      return NextResponse.json(
        {
          success: false,
          message: "Perjalanan belum berstatus ON_TRIP.",
        },
        { status: 409 }
      );
    }

    if (errorMessage === "USER_NOT_COMPLETE") {
      return NextResponse.json(
        {
          success: false,
          message: "Driver atau penumpang belum lengkap.",
        },
        { status: 409 }
      );
    }

    if (errorMessage === "COIN_NOT_LOCKED") {
      return NextResponse.json(
        {
          success: false,
          message: "Koin perjalanan belum terkunci.",
        },
        { status: 409 }
      );
    }

    if (errorMessage === "USER_NOT_FOUND") {
      return NextResponse.json(
        {
          success: false,
          message: "Akun driver atau penumpang tidak ditemukan.",
        },
        { status: 404 }
      );
    }

    if (
      errorMessage === "DRIVER_LOCKED_COIN_INVALID" ||
      errorMessage === "PASSENGER_LOCKED_COIN_INVALID"
    ) {
      return NextResponse.json(
        {
          success: false,
          message: "Saldo koin terkunci tidak valid.",
        },
        { status: 409 }
      );
    }

    return NextResponse.json(
      {
        success: false,
        message: "Gagal menyelesaikan perjalanan.",
      },
      { status: 500 }
    );
  }
}