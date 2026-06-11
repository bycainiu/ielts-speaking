const apiBaseUrl = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:18080';
const speechAssessmentUrl = process.env.SPEECH_ASSESSMENT_URL || 'http://localhost:8010';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: '/speech-assessment/:path*',
          destination: `${speechAssessmentUrl}/:path*`,
        },
      ],
      fallback: [
        {
          source: '/api/:path*',
          destination: `${apiBaseUrl}/api/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
