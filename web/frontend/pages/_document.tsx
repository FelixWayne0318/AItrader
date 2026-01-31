import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" className="dark">
      <Head>
        <link rel="icon" href="/favicon.ico" />
        <meta name="theme-color" content="#0a0a0f" />
        {/* Critical CSS - loaded inline to prevent FOUC and ensure layout works */}
        <style dangerouslySetInnerHTML={{ __html: `
          :root {
            --background: 222 47% 5%;
            --foreground: 210 40% 98%;
            --primary: 173 80% 50%;
            --muted: 217 33% 15%;
            --border: 217 33% 17%;
          }
          html, body { margin: 0; padding: 0; }
          body {
            background-color: hsl(222 47% 5%);
            color: hsl(210 40% 98%);
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
            -webkit-font-smoothing: antialiased;
          }
          /* Critical responsive classes - prevent layout flash */
          .hidden { display: none !important; }
          @media (max-width: 1023px) {
            .lg\\:flex, .lg\\:block { display: none !important; }
          }
          @media (min-width: 1024px) {
            .lg\\:hidden { display: none !important; }
            .lg\\:flex { display: flex !important; }
            .lg\\:block { display: block !important; }
          }
        `}} />
      </Head>
      <body className="bg-background text-foreground">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
