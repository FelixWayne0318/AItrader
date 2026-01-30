/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
  // i18n configuration for multi-language
  i18n: {
    locales: ['en', 'zh'],
    defaultLocale: 'en',
    localeDetection: true,
  },
};

module.exports = nextConfig;
