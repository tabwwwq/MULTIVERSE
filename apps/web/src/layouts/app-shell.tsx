import { FlaskConical } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { BrandLink } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { Breadcrumbs } from "@/layouts/breadcrumbs";
import { MobileNav } from "@/layouts/mobile-nav";
import { Sidebar } from "@/layouts/sidebar";

const REPOSITORY_URL = "https://github.com/tabwwwq/MULTIVERSE";

/** Shared frame for all 20 screens: skip link, sidebar or drawer, top bar, main, footer. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div id="app-frame" className="flex min-h-svh">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-10 flex min-h-16 items-center gap-2 border-b border-line bg-canvas/90 px-4 backdrop-blur-md md:px-8">
            <MobileNav />
            <div className="lg:hidden">
              <BrandLink compact />
            </div>
            <div className="min-w-0 flex-1">
              <Breadcrumbs />
            </div>
            <Badge tone="warning" icon={FlaskConical}>
              <span className="sm:hidden">Prototype</span>
              <span className="hidden sm:inline">Prototype, demo data only</span>
            </Badge>
          </header>
          <main
            id="main"
            tabIndex={-1}
            className="mx-auto w-full max-w-content flex-1 px-4 py-10 md:px-8 md:py-14"
          >
            {children}
          </main>
          <footer className="border-t border-line px-4 py-6 text-small text-ink-muted md:px-8">
            <div className="mx-auto flex max-w-content flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <p>
                MULTIVERSE is a research prototype. It gives no investment advice, and demo data is
                synthetic.
              </p>
              <ul className="flex flex-wrap gap-x-5 gap-y-2">
                <li>
                  <Link href="/methodology" className="hover:text-ink">
                    Methodology
                  </Link>
                </li>
                <li>
                  <Link href="/design-system" className="hover:text-ink">
                    Design system
                  </Link>
                </li>
                <li>
                  <a href={REPOSITORY_URL} className="hover:text-ink" rel="noreferrer">
                    Source code
                  </a>
                </li>
              </ul>
            </div>
          </footer>
        </div>
      </div>
    </>
  );
}
