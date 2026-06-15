"use client";

import { Brand } from "@/components/brand";
import { NavList } from "@/components/nav-items";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * Desktop persistent navigation drawer (Material 3). Hidden on mobile —
 * the mobile drawer lives in `AppShell` as a modal Sheet.
 */
export function Navigation() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-sidebar-border bg-sidebar md:flex">
      <div className="flex h-16 items-center px-5">
        <Brand />
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        <NavList />
      </nav>
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <span className="text-[11px] text-muted-foreground">Platform · v0.1</span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
