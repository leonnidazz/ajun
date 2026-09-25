import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const tripId = String(body.tripId ?? "").trim();
    const qrToken = String(body.qrToken ?? "").trim();

    if (!tripId || !qrToken) {
      return NextResponse.json(
        {
          success: false,
          message: "tripId dan qrToken wajib diisi.",
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
            qrToken: true,
          },
        },
        passenger: {
          select: {
            id: true,
            username: true,
            email: true,
            qrToken: true,
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

    if (trip.status !== "LOCKED") {
      return NextResponse.json(
        {
          success: false,
          message: "Pesanan belum siap untuk diverifikasi.",
        },
        { status: 409 }
      );
    }

    if (!trip.driverId || !trip.passengerId || !trip.driver || !trip.passenger) {
      return NextResponse.json(
        {
          success: false,
          message: "Data driver atau penumpang belum lengkap.",
        },
        { status: 409 }
      );
    }

    const qrValid =
      qrToken === trip.driver.qrToken ||
      qrToken === trip.passenger.qrToken;

    if (!qrValid) {
      return NextResponse.json(
        {
          success: false,
          message: "QR Token tidak valid untuk perjalanan ini.",
        },
        { status: 401 }
      );
    }

    const updatedTrip = await prisma.trip.update({
      where: {
        id: tripId,
      },
      data: {
        status: "VERIFIED",
        verifiedAt: new Date(),
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
      message: "Perjalanan berhasil diverifikasi.",
      trip: updatedTrip,
    });
  } catch (error) {
    console.error("VERIFY_TRIP_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal melakukan verifikasi perjalanan.",
      },
      { status: 500 }
    );
  }
}