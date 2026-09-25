import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const userId = searchParams.get("userId")?.trim();

    if (!userId) {
      return NextResponse.json(
        {
          success: false,
          message: "userId wajib diisi.",
        },
        { status: 400 }
      );
    }

    const user = await prisma.user.findUnique({
      where: {
        id: userId,
      },
      select: {
        id: true,
        username: true,
        email: true,
      },
    });

    if (!user) {
      return NextResponse.json(
        {
          success: false,
          message: "User tidak ditemukan.",
        },
        { status: 404 }
      );
    }

    const trips = await prisma.trip.findMany({
      where: {
        OR: [
          {
            driverId: userId,
          },
          {
            passengerId: userId,
          },
        ],
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
      trips,
    });
  } catch (error) {
    console.error("GET_MY_TRIPS_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal mengambil pesanan user.",
      },
      { status: 500 }
    );
  }
}