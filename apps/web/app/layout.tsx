import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
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
    <html lang="en" className="dark">
      <body
        suppressHydrationWarning
        className={`${inter.variable} ${playfair.variable} font-sans min-h-screen bg-academic-navy text-slate-200 antialiased selection:bg-academic-teal/30`}
      >
        <div className="fixed inset-0 z-[-1] bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-academic-slate via-academic-navy to-academic-navy"></div>
        {children}
      </body>
    </html>
  );
}
