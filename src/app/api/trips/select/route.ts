import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const tripId = String(body.tripId ?? "").trim();
    const passengerId = String(body.passengerId ?? "").trim();

    if (!tripId || !passengerId) {
      return NextResponse.json(
        {
          success: false,
          message: "tripId dan passengerId wajib diisi.",
        },
        { status: 400 }
      );
    }

    const passenger = await prisma.user.findUnique({
      where: {
        id: passengerId,
      },
      select: {
        id: true,
        username: true,
        email: true,
      },
    });

    if (!passenger) {
      return NextResponse.json(
        {
          success: false,
          message: "Akun penumpang tidak ditemukan.",
        },
        { status: 404 }
      );
    }

    const trip = await prisma.trip.findUnique({
      where: {
        id: tripId,
      },
      select: {
        id: true,
        driverId: true,
        passengerId: true,
        destination: true,
        status: true,
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

    if (trip.driverId === passengerId) {
      return NextResponse.json(
        {
          success: false,
          message: "Pembuat pesanan tidak dapat memilih pesanannya sendiri.",
        },
        { status: 400 }
      );
    }

    if (trip.status !== "AVAILABLE") {
      return NextResponse.json(
        {
          success: false,
          message: "Pesanan sudah tidak tersedia.",
        },
        { status: 409 }
      );
    }

    const updatedTrip = await prisma.trip.update({
      where: {
        id: tripId,
      },
      data: {
  passengerId,
  status: "WAITING_CONFIRMATION",
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
      message: "Pesanan berhasil dipilih.",
      trip: updatedTrip,
    });
  } catch (error) {
    console.error("SELECT_TRIP_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal memilih pesanan.",
      },
      { status: 500 }
    );
  }
}