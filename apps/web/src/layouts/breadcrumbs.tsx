"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";
import { buildBreadcrumbs } from "@/navigation/breadcrumbs";

export function Breadcrumbs() {
  const crumbs = buildBreadcrumbs(usePathname());
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-small">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 ? (
                <li aria-hidden="true" className="hidden text-ink-muted sm:block">
                  <ChevronRight className="size-3.5" />
                </li>
              ) : null}
              <li
                className={
                  last ? "min-w-0 truncate text-ink" : "hidden shrink-0 text-ink-muted sm:block"
                }
              >
                {last ? (
                  <span aria-current="page">{crumb.label}</span>
                ) : crumb.href ? (
                  <Link href={crumb.href} className="rounded-control hover:text-ink">
                    {crumb.label}
                  </Link>
                ) : (
                  crumb.label
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
