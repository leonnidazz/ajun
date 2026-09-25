import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const userId = String(body.userId ?? "").trim();
    const amount = Number(body.amount ?? 0);

    if (!userId || !Number.isInteger(amount) || amount <= 0) {
      return NextResponse.json(
        {
          success: false,
          message: "userId dan amount harus diisi dengan benar.",
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
        coinBalance: true,
        lockedCoins: true,
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

    const updatedUser = await prisma.user.update({
      where: {
        id: userId,
      },
      data: {
        coinBalance: {
          increment: amount,
        },
      },
      select: {
        id: true,
        username: true,
        email: true,
        coinBalance: true,
        lockedCoins: true,
      },
    });

    return NextResponse.json({
      success: true,
      message: `Saldo koin ${user.username} berhasil ditambah ${amount} koin.`,
      user: updatedUser,
    });
  } catch (error) {
    console.error("TEST_COINS_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal menambah saldo koin.",
      },
      { status: 500 }
    );
  }
}