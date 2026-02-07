import { PrismaClient } from '@prisma/client';

let prisma: PrismaClient | null = null;

export const getPrismaClient = () => {
  if (!process.env.DATABASE_URL) return null;
  if (!prisma) {
    prisma = new PrismaClient();
  }
  return prisma;
};
