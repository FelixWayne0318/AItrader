import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Algvex - AI-Powered Crypto Trading",
  description:
    "Advanced algorithmic trading powered by DeepSeek AI and multi-agent decision system. Follow my trades on major exchanges.",
  keywords: [
    "crypto trading",
    "algorithmic trading",
    "copy trading",
    "AI trading",
    "Bitcoin",
    "cryptocurrency",
  ],
  openGraph: {
    title: "Algvex - AI-Powered Crypto Trading",
    description:
      "Advanced algorithmic trading powered by DeepSeek AI. Follow my trades on Binance, Bybit, and more.",
    type: "website",
    url: "https://algvex.com",
  },
  twitter: {
    card: "summary_large_image",
    title: "Algvex - AI-Powered Crypto Trading",
    description: "Advanced algorithmic trading powered by DeepSeek AI",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
