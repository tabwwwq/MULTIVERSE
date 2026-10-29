/*
 * External links are allowed only to the official sources of docs/04, over HTTPS,
 * without credentials or custom ports. Anything else is not rendered as a link.
 */

const ALLOWED_HOSTS = new Set([
  "www.sec.gov",
  "data.sec.gov",
  "fred.stlouisfed.org",
  "alfred.stlouisfed.org",
  "api.stlouisfed.org",
  "data.ecb.europa.eu",
  "data-api.ecb.europa.eu",
  "www.ecb.europa.eu",
  "data.worldbank.org",
  "api.worldbank.org",
  "www.worldbank.org",
  "datahelpdesk.worldbank.org",
  "datacatalog.worldbank.org",
  "datatopics.worldbank.org",
]);

export function safeExternalUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
  return ALLOWED_HOSTS.has(url.hostname) ? url.href : null;
}
