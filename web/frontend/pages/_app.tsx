import type { AppProps } from "next/app";
import { Inter, JetBrains_Mono } from "next/font/google";
import "@/app/globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export default function App({ Component, pageProps }: AppProps) {
  return (
    <main
      className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased min-h-screen`}
    >
      <Component {...pageProps} />
    </main>
  );
}
