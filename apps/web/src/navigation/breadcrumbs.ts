import { SECTIONS, groupLabel } from "@/navigation/sections";

export interface Crumb {
  label: string;
  /** Absent for the current page and for group labels, which are not pages. */
  href?: string;
}

const EXTRA_PAGES: Record<string, string> = {
  "/design-system": "Design system",
};

/** Label of a page nested under a section, e.g. one company under the dossier. */
const NESTED_LABELS: Record<string, string> = {
  "/dossier": "Company profile",
};

/** Overview › Group › Page (› Detail) for a pathname. Unknown paths fall back to the overview. */
export function buildBreadcrumbs(pathname: string): Crumb[] {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const home: Crumb = { label: "Overview", href: "/" };
  if (path === "/") return [{ label: "Overview" }];

  const extra = EXTRA_PAGES[path];
  if (extra) return [home, { label: extra }];

  const exact = SECTIONS.find((candidate) => candidate.href === path);
  const parent = exact
    ? undefined
    : SECTIONS.find((candidate) => candidate.href !== "/" && path.startsWith(`${candidate.href}/`));
  const section = exact ?? parent;
  if (!section) return [home];

  const trail: Crumb[] =
    section.group === "overview" ? [home] : [home, { label: groupLabel(section.group) }];
  if (exact) return [...trail, { label: section.title }];
  return [
    ...trail,
    { label: section.title, href: section.href },
    { label: NESTED_LABELS[section.href] ?? "Details" },
  ];
}
