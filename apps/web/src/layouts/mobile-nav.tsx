"use client";

import { Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BrandLink } from "@/components/brand/logo";
import { NavLinks } from "@/layouts/nav-links";
import { useIsClient } from "@/lib/client-state";

/*
 * Navigation drawer for widths below 1024px, built as the navigation-drawer
 * guidance describes: a popover="manual" element in the top layer, a horizontal
 * scroll-snap container for native swipe-to-close, a scroll-driven backdrop, and an
 * IntersectionObserver as the single source of truth for open / closed state.
 * The drawer is portalled to <body> so making the page inert does not make it inert.
 */

const FRAME_ID = "app-frame";

function nextFrames(): Promise<void> {
  return new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );
}

export function MobileNav() {
  const mounted = useIsClient();
  const [expanded, setExpanded] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const openRef = useRef(false);
  const pathname = usePathname();

  const closeDrawer = useCallback(() => {
    const scroller = scrollerRef.current;
    // Scroll back to the closed snap stop; the observer hides the popover afterwards.
    if (scroller && openRef.current)
      scroller.scrollTo({ left: scroller.offsetWidth, behavior: "auto" });
  }, []);

  const openDrawer = useCallback(async () => {
    const drawer = drawerRef.current;
    const scroller = scrollerRef.current;
    if (!drawer || !scroller) return;
    drawer.showPopover();
    if (!CSS.supports("scroll-initial-target", "nearest")) {
      scroller.scrollTo({ left: scroller.offsetWidth, behavior: "instant" });
      await nextFrames();
    }
    scroller.scrollTo({ left: 0, behavior: "auto" });
  }, []);

  useEffect(() => {
    if (!mounted) return;
    const drawer = drawerRef.current;
    const scroller = scrollerRef.current;
    const sheet = sheetRef.current;
    if (!drawer || !scroller || !sheet) return;

    const setFrameInert = (inert: boolean) => {
      const frame = document.getElementById(FRAME_ID);
      if (frame) frame.inert = inert;
    };
    const onOpened = () => {
      openRef.current = true;
      setFrameInert(true);
      setExpanded(true);
      sheet.focus();
    };
    const onClosed = () => {
      const wasOpen = openRef.current;
      openRef.current = false;
      if (drawer.matches(":popover-open")) drawer.hidePopover();
      setFrameInert(false);
      setExpanded(false);
      if (wasOpen) triggerRef.current?.focus();
    };

    const visibleThreshold = 1 / window.innerWidth;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries.at(-1);
        if (!entry) return;
        if (entry.intersectionRatio < visibleThreshold) onClosed();
        if (entry.intersectionRatio === 1) onOpened();
      },
      { root: drawer, threshold: [visibleThreshold, 1] },
    );
    observer.observe(sheet);

    // Backdrop fade where scroll-driven animations are not supported.
    const onScroll = () => {
      const ratio = 1 - scroller.scrollLeft / sheet.offsetWidth;
      drawer.style.setProperty("--drawer-backdrop", String(Math.min(1, Math.max(0, ratio))));
    };
    const needsScrollFallback = !CSS.supports("animation-timeline: scroll()");
    if (needsScrollFallback) scroller.addEventListener("scroll", onScroll, { passive: true });

    // Light dismiss: a tap on the dimmed area outside the sheet.
    const onDrawerClick = (event: MouseEvent) => {
      if (event.target instanceof Node && !sheet.contains(event.target)) closeDrawer();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && openRef.current) closeDrawer();
    };
    drawer.addEventListener("click", onDrawerClick);
    document.addEventListener("keydown", onKeyDown);

    return () => {
      observer.disconnect();
      if (needsScrollFallback) scroller.removeEventListener("scroll", onScroll);
      drawer.removeEventListener("click", onDrawerClick);
      document.removeEventListener("keydown", onKeyDown);
      setFrameInert(false);
    };
  }, [mounted, closeDrawer]);

  // Close after navigating to another page.
  useEffect(() => {
    closeDrawer();
  }, [pathname, closeDrawer]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => void openDrawer()}
        aria-label="Open navigation"
        aria-expanded={expanded}
        aria-controls="nav-drawer"
        className="flex size-12 items-center justify-center rounded-control text-ink hover:bg-inset lg:hidden"
      >
        <Menu aria-hidden="true" className="size-5" />
      </button>
      {mounted
        ? createPortal(
            <div ref={drawerRef} id="nav-drawer" popover="manual" className="Drawer">
              <div ref={scrollerRef} className="Drawer-scroller">
                <nav ref={sheetRef} tabIndex={-1} aria-label="Main" className="Drawer-sheet">
                  <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-4">
                    <BrandLink onNavigate={closeDrawer} />
                    <button
                      type="button"
                      onClick={closeDrawer}
                      aria-label="Close navigation"
                      className="flex size-12 items-center justify-center rounded-control text-ink-muted hover:bg-inset hover:text-ink"
                    >
                      <X aria-hidden="true" className="size-5" />
                    </button>
                  </div>
                  <div className="px-3 pb-6">
                    <NavLinks onNavigate={closeDrawer} />
                  </div>
                </nav>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
