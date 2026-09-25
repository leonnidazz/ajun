import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
    const users = await prisma.user.findMany({
      select: {
  id: true,
  username: true,
  email: true,
  coinBalance: true,
  qrToken: true,
},
      orderBy: {
        username: "asc",
      },
    });

    return NextResponse.json({
      success: true,
      message: "Database AJUN berhasil terhubung.",
      userCount: users.length,
      users,
    });
  } catch (error) {
    console.error("Database error:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal terhubung ke database.",
      },
      { status: 500 }
    );
  }
}