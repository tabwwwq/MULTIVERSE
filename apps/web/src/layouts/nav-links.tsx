"use client";

import { Clock } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { NAV_GROUPS, SECTIONS, formatStage } from "@/navigation/sections";

interface NavLinksProps {
  /** Icons only; labels stay available to screen readers. */
  collapsed?: boolean;
  onNavigate?: () => void;
}

export function NavLinks({ collapsed = false, onNavigate }: NavLinksProps) {
  const pathname = usePathname();
  return (
    <div className="flex flex-col gap-5">
      {NAV_GROUPS.map((group) => {
        const sections = SECTIONS.filter((section) => section.group === group.id);
        const headingId = `nav-group-${group.id}`;
        return (
          <div key={group.id} role="group" aria-labelledby={headingId}>
            <p
              id={headingId}
              className={cn("mb-1 px-3 text-micro text-ink-muted", collapsed && "sr-only")}
            >
              {group.label}
            </p>
            <ul className="flex flex-col gap-0.5">
              {sections.map((section) => {
                const active = pathname === section.href;
                const Icon = section.icon;
                const planned = section.status === "planned";
                return (
                  <li key={section.href}>
                    <Link
                      href={section.href}
                      {...(onNavigate ? { onClick: onNavigate } : {})}
                      aria-current={active ? "page" : undefined}
                      title={
                        planned
                          ? `${section.title}: planned for ${formatStage(section.stage)}`
                          : collapsed
                            ? section.title
                            : undefined
                      }
                      className={cn(
                        "group relative flex min-h-10 items-center gap-3 rounded-control px-3 text-small",
                        "transition-colors duration-150",
                        active
                          ? "bg-inset text-ink"
                          : "text-ink-muted hover:bg-inset/60 hover:text-ink",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      {active ? (
                        <span
                          aria-hidden="true"
                          className="absolute inset-y-2 left-0 w-0.5 rounded-pill bg-mint"
                        />
                      ) : null}
                      <Icon
                        aria-hidden="true"
                        className={cn("size-4 shrink-0", active && "text-mint")}
                      />
                      <span className={cn("min-w-0 flex-1 truncate", collapsed && "sr-only")}>
                        {section.title}
                      </span>
                      {planned ? (
                        <>
                          <Clock
                            aria-hidden="true"
                            className={cn("size-3.5 shrink-0 opacity-70", collapsed && "hidden")}
                          />
                          <span className="sr-only">planned, {formatStage(section.stage)}</span>
                        </>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      <p
        className={cn(
          "flex items-center gap-2 px-3 text-micro text-ink-muted",
          collapsed && "sr-only",
        )}
      >
        <Clock aria-hidden="true" className="size-3.5 shrink-0" />
        Planned, not built yet
      </p>
    </div>
  );
}
