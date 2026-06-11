const faviconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#0B132B"/>
  <circle cx="32" cy="32" r="19" fill="none" stroke="#D4AF37" stroke-width="5"/>
  <path d="M21 31h22v15H21z" fill="none" stroke="#F8FAFC" stroke-width="4" stroke-linejoin="round"/>
  <path d="M26 31v-7h12v7" fill="none" stroke="#F8FAFC" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M28 38v3M36 38v3" stroke="#F8FAFC" stroke-width="3" stroke-linecap="round"/>
</svg>`;

export function GET() {
  return new Response(faviconSvg, {
    headers: {
      "Cache-Control": "public, max-age=86400",
      "Content-Type": "image/svg+xml; charset=utf-8",
    },
  });
}
