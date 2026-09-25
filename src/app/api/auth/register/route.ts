import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { prisma } from "@/lib/prisma";
import crypto from "crypto";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const username = String(body.username ?? "")
      .trim()
      .toLowerCase();

    const email = String(body.email ?? "")
      .trim()
      .toLowerCase();

    const password = String(body.password ?? "");

    if (!username || !email || !password) {
      return NextResponse.json(
        {
          success: false,
          message: "Username, email, dan password wajib diisi.",
        },
        { status: 400 }
      );
    }

    if (password.length < 8) {
      return NextResponse.json(
        {
          success: false,
          message: "Password minimal 8 karakter.",
        },
        { status: 400 }
      );
    }

    const existingUser = await prisma.user.findFirst({
      where: {
        OR: [
          {
            username,
          },
          {
            email,
          },
        ],
      },
    });

    if (existingUser) {
      return NextResponse.json(
        {
          success: false,
          message: "Username atau email sudah digunakan.",
        },
        { status: 409 }
      );
    }

    const passwordHash = await bcrypt.hash(password, 12);

    const referralCode = `AJUN-${crypto
      .randomBytes(5)
      .toString("hex")
      .toUpperCase()}`;

    const qrToken = crypto.randomUUID();

    const user = await prisma.user.create({
      data: {
        username,
        email,
        passwordHash,
        referralCode,
        qrToken,
        coinBalance: 0,
        lockedCoins: 0,
      },
    });

    return NextResponse.json(
      {
        success: true,
        message: "Akun AJUN berhasil dibuat.",
        user: {
          id: user.id,
          username: user.username,
          email: user.email,
        },
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("REGISTER_ERROR:", error);

    return NextResponse.json(
      {
        success: false,
        message: "Terjadi kesalahan saat membuat akun.",
      },
      { status: 500 }
    );
  }
}