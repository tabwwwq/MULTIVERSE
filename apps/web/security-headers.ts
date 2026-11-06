/*
 * Headers of every page (Stage 24). The app is static and talks only to the API of this machine.
 *
 * Next.js writes inline bootstrap scripts into static pages. A nonce would force every page to
 * render per request, so scripts keep 'unsafe-inline': the guard against injected markup is that
 * the code has no HTML sink at all, and a test keeps it that way (docs/security/issue-register.md,
 * SEC-015).
 */

const API_ORIGIN = "http://127.0.0.1:8000";

export function contentSecurityPolicy(development: boolean): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self' ${API_ORIGIN}${development ? " ws://127.0.0.1:3000 ws://localhost:3000" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function securityHeaders(development: boolean): { key: string; value: string }[] {
  return [
    { key: "Content-Security-Policy", value: contentSecurityPolicy(development) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
    { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  ];
}
