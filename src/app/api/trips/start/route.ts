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

    const trip = await prisma.trip.findUnique({
      where: {
        id: tripId,
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

    if (!trip) {
      return NextResponse.json(
        {
          success: false,
          message: "Pesanan tidak ditemukan.",
        },
        { status: 404 }
      );
    }

    if (trip.status !== "VERIFIED") {
      return NextResponse.json(
        {
          success: false,
          message: "Perjalanan belum terverifikasi.",
        },
        { status: 409 }
      );
    }

    if (!trip.driverId || !trip.passengerId) {
      return NextResponse.json(
        {
          success: false,
          message: "Driver atau penumpang belum lengkap.",
        },
        { status: 409 }
      );
    }

    if (!trip.driverCoinLocked || !trip.passengerCoinLocked) {
      return NextResponse.json(
        {
          success: false,
          message: "Koin perjalanan belum terkunci.",
        },
        { status: 409 }
      );
    }

    const updatedTrip = await prisma.trip.update({
      where: {
        id: tripId,
      },
      data: {
        status: "ON_TRIP",
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

    return NextResponse.json({
      success: true,
      message: "Perjalanan dimulai.",
      trip: updatedTrip,
    });
  } catch (error) {
    console.error("START_TRIP_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal memulai perjalanan.",
      },
      { status: 500 }
    );
  }
}