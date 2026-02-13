import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" className="dark">
      <Head>
        <link rel="icon" href="/favicon.ico" />
        <meta name="theme-color" content="#0a0a0f" />
        {/*
          NOTE: We do NOT use inline critical CSS here.
          Tailwind CSS should handle all styling through proper content scanning.
          If responsive classes don't work, the fix is:
          1. Clear .next cache: rm -rf .next
          2. Rebuild: npm run build
          3. Restart server: pm2 restart algvex-frontend

          Reference: https://github.com/tailwindlabs/tailwindcss/discussions/8521
        */}
      </Head>
      <body className="bg-background text-foreground">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
