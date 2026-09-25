import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { prisma } from "@/lib/prisma";

export async function POST() {
  try {
    const newPassword = "12345678";

    const passwordHash = await bcrypt.hash(newPassword, 12);

    const user = await prisma.user.update({
      where: {
        username: "test04",
      },
      data: {
        passwordHash,
      },
      select: {
        id: true,
        username: true,
        email: true,
      },
    });

    return NextResponse.json({
      success: true,
      message: "Password test04 berhasil direset.",
      user,
    });
  } catch (error) {
    console.error("RESET_TEST_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Gagal mereset password test04.",
      },
      { status: 500 }
    );
  }
}