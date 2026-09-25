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

    if (trip.passengerId !== passengerId) {
      return NextResponse.json(
        {
          success: false,
          message: "Hanya penumpang yang memilih pesanan ini yang dapat melakukan konfirmasi.",
        },
        { status: 403 }
      );
    }

    if (!trip.driverId) {
      return NextResponse.json(
        {
          success: false,
          message: "Driver belum tersedia.",
        },
        { status: 409 }
      );
    }

    if (trip.status !== "WAITING_CONFIRMATION") {
      return NextResponse.json(
        {
          success: false,
          message: "Pesanan belum menunggu konfirmasi penumpang.",
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
        matchedAt: trip.matchedAt ?? new Date(),
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
      message: "Perjalanan berhasil di-match.",
      trip: updatedTrip,
    });
  } catch (error) {
    console.error("MATCH_TRIP_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal melakukan match perjalanan.",
      },
      { status: 500 }
    );
  }
}