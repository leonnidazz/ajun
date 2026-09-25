import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const tripId = String(body.tripId ?? "").trim();
    const driverId = String(body.driverId ?? "").trim();

    if (!tripId || !driverId) {
      return NextResponse.json(
        {
          success: false,
          message: "tripId dan driverId wajib diisi.",
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

    if (trip.driverId !== driverId) {
      return NextResponse.json(
        {
          success: false,
          message: "Hanya driver pemilik pesanan yang dapat melakukan konfirmasi.",
        },
        { status: 403 }
      );
    }

    if (!trip.passengerId) {
      return NextResponse.json(
        {
          success: false,
          message: "Belum ada penumpang yang memilih pesanan ini.",
        },
        { status: 409 }
      );
    }

    if (trip.status !== "WAITING_CONFIRMATION") {
  return NextResponse.json(
    {
      success: false,
      message: "Pesanan belum berada pada status WAITING_CONFIRMATION.",
    },
    { status: 409 }
  );
}

    const updatedTrip = await prisma.trip.update({
      where: {
        id: tripId,
      },
      data: {
  status: "MATCHED",
  matchedAt: new Date(),
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
      message: "Penumpang berhasil dikonfirmasi.",
      trip: updatedTrip,
    });
  } catch (error) {
    console.error("CONFIRM_TRIP_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal mengonfirmasi penumpang.",
      },
      { status: 500 }
    );
  }
}