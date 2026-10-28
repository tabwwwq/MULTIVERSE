import { SECTIONS, groupLabel } from "@/navigation/sections";

export interface Crumb {
  label: string;
  /** Absent for the current page and for group labels, which are not pages. */
  href?: string;
}

const EXTRA_PAGES: Record<string, string> = {
  "/design-system": "Design system",
};

/** Overview › Group › Page for a pathname. Unknown paths fall back to the overview only. */
export function buildBreadcrumbs(pathname: string): Crumb[] {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const home: Crumb = { label: "Overview", href: "/" };
  if (path === "/") return [{ label: "Overview" }];

  const extra = EXTRA_PAGES[path];
  if (extra) return [home, { label: extra }];

  const section = SECTIONS.find((candidate) => candidate.href === path);
  if (!section) return [home];
  if (section.group === "overview") return [home, { label: section.title }];
  return [home, { label: groupLabel(section.group) }, { label: section.title }];
}
