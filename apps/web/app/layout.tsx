import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";

import { AuthSessionGuard } from "@/components/auth/AuthSessionGuard";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const playfair = Playfair_Display({ subsets: ["latin"], variable: "--font-playfair" });

export const metadata: Metadata = {
  title: "IELTS Speaking Agent",
  description: "Live IELTS Speaking practice and mock exams.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        suppressHydrationWarning
        className={`${inter.variable} ${playfair.variable} font-sans min-h-screen bg-background text-foreground antialiased selection:bg-academic-accent/20`}
      >
        <AuthSessionGuard />
        {children}
      </body>
    </html>
  );
}
