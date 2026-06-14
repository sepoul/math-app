"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { Brand } from "@/components/brand";
import { Navigation } from "@/components/navigation";
import { NavList } from "@/components/nav-items";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

/**
 * Responsive application shell (Material 3):
 *  - ≥ md: persistent left navigation drawer + content inset (`md:pl-64`).
 *  - < md: a sticky top app bar with a hamburger that opens a modal
 *    navigation drawer (Sheet). Content is full-width.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen">
      <Navigation />

      {/* Mobile top app bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-1 border-b border-border bg-background/85 px-2 backdrop-blur-md md:hidden">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open navigation"
          onClick={() => setOpen(true)}
        >
          <Menu />
        </Button>
        <Brand className="ml-1" />
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>

      {/* Mobile modal navigation drawer */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="left"
          showCloseButton={false}
          className="w-72 max-w-[80vw] gap-0 border-r border-sidebar-border bg-sidebar p-0"
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="flex h-14 items-center px-5">
            <Brand onClick={() => setOpen(false)} />
          </div>
          <nav className="flex-1 overflow-y-auto px-3 py-2">
            <NavList onNavigate={() => setOpen(false)} />
          </nav>
        </SheetContent>
      </Sheet>

      <main className="md:pl-64">{children}</main>
    </div>
  );
}
