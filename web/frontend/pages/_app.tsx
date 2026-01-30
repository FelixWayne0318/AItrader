import { useEffect } from "react";
import type { AppProps } from "next/app";
import { Inter, JetBrains_Mono } from "next/font/google";
import Head from "next/head";
import useSWR from "swr";
import "@/app/globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

const fetcher = (url: string) => fetch(url).then((res) => res.json());

export default function App({ Component, pageProps }: AppProps) {
  // Fetch branding settings for dynamic favicon
  const { data: branding } = useSWR("/api/public/site-branding", fetcher, {
    refreshInterval: 300000, // 5 minutes
  });

  // Update favicon dynamically
  useEffect(() => {
    if (branding?.favicon_url) {
      const link: HTMLLinkElement =
        document.querySelector("link[rel*='icon']") ||
        document.createElement("link");
      link.type = "image/x-icon";
      link.rel = "shortcut icon";
      link.href = branding.favicon_url;
      document.head.appendChild(link);
    }
  }, [branding?.favicon_url]);

  return (
    <>
      <Head>
        <title>{branding?.site_name || "AlgVex"} - AI Trading</title>
      </Head>
      <main
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased min-h-screen`}
      >
        <Component {...pageProps} />
      </main>
    </>
  );
}
