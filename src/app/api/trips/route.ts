import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const driverId = String(body.driverId ?? "").trim();
    const destination = String(body.destination ?? "").trim();

    if (!driverId || !destination) {
      return NextResponse.json(
        {
          success: false,
          message: "driverId dan tujuan wajib diisi.",
        },
        { status: 400 }
      );
    }

    const driver = await prisma.user.findUnique({
      where: {
        id: driverId,
      },
      select: {
        id: true,
        username: true,
        email: true,
      },
    });

    if (!driver) {
      return NextResponse.json(
        {
          success: false,
          message: "Akun driver tidak ditemukan.",
        },
        { status: 404 }
      );
    }

    const trip = await prisma.trip.create({
      data: {
        driverId: driver.id,
        destination,
        status: "AVAILABLE",
      },
      include: {
        driver: {
          select: {
            id: true,
            username: true,
            email: true,
          },
        },
      },
    });

    return NextResponse.json(
      {
        success: true,
        message: "Pesanan antar berhasil dibuat.",
        trip,
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("CREATE_TRIP_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal membuat pesanan antar.",
      },
      { status: 500 }
    );
  }
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tripId = searchParams.get("tripId");

    // Jika tripId diberikan, ambil detail satu pesanan
    if (tripId) {
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

      return NextResponse.json({
        success: true,
        trip,
      });
    }

    // Jika tidak ada tripId, tampilkan pesanan yang masih tersedia
    const trips = await prisma.trip.findMany({
      where: {
        status: "AVAILABLE",
      },
      orderBy: {
        createdAt: "desc",
      },
      include: {
        driver: {
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
      trips,
    });
  } catch (error) {
    console.error("GET_TRIPS_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal mengambil data pesanan.",
      },
      { status: 500 }
    );
  }
}