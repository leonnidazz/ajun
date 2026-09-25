import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const COIN_COST = 1;

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

      if (trip.status !== "MATCHED") {
        throw new Error("TRIP_NOT_MATCHED");
      }

      if (!trip.driverId || !trip.passengerId) {
        throw new Error("USER_NOT_COMPLETE");
      }

      if (trip.driverCoinLocked || trip.passengerCoinLocked) {
        throw new Error("COIN_ALREADY_LOCKED");
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

      if (driver.coinBalance < COIN_COST) {
        throw new Error("DRIVER_COIN_INSUFFICIENT");
      }

      if (passenger.coinBalance < COIN_COST) {
        throw new Error("PASSENGER_COIN_INSUFFICIENT");
      }

      const updatedDriver = await tx.user.update({
        where: {
          id: driver.id,
        },
        data: {
          coinBalance: {
            decrement: COIN_COST,
          },
          lockedCoins: {
            increment: COIN_COST,
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
            decrement: COIN_COST,
          },
          lockedCoins: {
            increment: COIN_COST,
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
          driverCoinLocked: true,
          passengerCoinLocked: true,
          status: "LOCKED",
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
      message: "Koin driver dan penumpang berhasil dikunci.",
      trip: result.trip,
      driver: result.driver,
      passenger: result.passenger,
    });
  } catch (error) {
    console.error("LOCK_TRIP_COINS_ERROR:", error);

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

    if (errorMessage === "TRIP_NOT_MATCHED") {
      return NextResponse.json(
        {
          success: false,
          message: "Pesanan belum berstatus MATCHED.",
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

    if (errorMessage === "COIN_ALREADY_LOCKED") {
      return NextResponse.json(
        {
          success: false,
          message: "Koin untuk pesanan ini sudah dikunci.",
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

    if (errorMessage === "DRIVER_COIN_INSUFFICIENT") {
      return NextResponse.json(
        {
          success: false,
          message: "Koin driver tidak mencukupi.",
        },
        { status: 409 }
      );
    }

    if (errorMessage === "PASSENGER_COIN_INSUFFICIENT") {
      return NextResponse.json(
        {
          success: false,
          message: "Koin penumpang tidak mencukupi.",
        },
        { status: 409 }
      );
    }

    return NextResponse.json(
      {
        success: false,
        message: "Gagal mengunci koin perjalanan.",
      },
      { status: 500 }
    );
  }
}