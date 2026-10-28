"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { BrandLink } from "@/components/brand/logo";
import { NavLinks } from "@/layouts/nav-links";
import { usePersistedFlag } from "@/lib/client-state";
import { cn } from "@/lib/cn";

const STORAGE_KEY = "multiverse.sidebar.collapsed";

/** Desktop navigation (≥ 1024px). Below that width the mobile drawer takes over. */
export function Sidebar() {
  const [collapsed, setCollapsed] = usePersistedFlag(STORAGE_KEY, false);
  const toggle = () => setCollapsed(!collapsed);

  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-svh shrink-0 flex-col border-r border-line bg-surface lg:flex",
        "transition-[width] duration-200 ease-standard motion-reduce:transition-none",
        collapsed ? "w-[72px]" : "w-[248px]",
      )}
    >
      <div className={cn("flex items-center px-4 pt-3 pb-4", collapsed && "justify-center px-2")}>
        <BrandLink compact={collapsed} />
      </div>
      <nav
        id="sidebar-nav"
        aria-label="Main"
        className={cn("min-h-0 flex-1 overflow-y-auto px-3 pb-4", collapsed && "px-2")}
      >
        <NavLinks collapsed={collapsed} />
      </nav>
      <div className={cn("border-t border-line p-3", collapsed && "px-2")}>
        <button
          type="button"
          onClick={toggle}
          aria-controls="sidebar-nav"
          aria-expanded={!collapsed}
          className={cn(
            "flex min-h-10 w-full items-center gap-3 rounded-control px-3 text-small text-ink-muted hover:bg-inset hover:text-ink",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen aria-hidden="true" className="size-4" />
          ) : (
            <PanelLeftClose aria-hidden="true" className="size-4" />
          )}
          <span className={cn(collapsed && "sr-only")}>
            {collapsed ? "Expand navigation" : "Collapse navigation"}
          </span>
        </button>
      </div>
    </aside>
  );
}
