"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Boxes,
  Calculator,
  FileType2,
  History,
  Home,
  MessagesSquare,
  NotebookPen,
  Shapes,
  Sigma,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  match: (pathname: string) => boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: Home, match: (p) => p === "/" },
  { href: "/math-qa", label: "Math Q&A", icon: Calculator, match: (p) => p.startsWith("/math-qa") },
  { href: "/math-notes", label: "Daily notes", icon: NotebookPen, match: (p) => p.startsWith("/math-notes") },
  { href: "/math-conversation", label: "Conversation", icon: MessagesSquare, match: (p) => p.startsWith("/math-conversation") },
  { href: "/workflows", label: "Workflows", icon: Workflow, match: (p) => p.startsWith("/workflows") },
  { href: "/jobs", label: "Jobs", icon: History, match: (p) => p.startsWith("/jobs") },
  { href: "/artifacts", label: "Artifacts", icon: Boxes, match: (p) => p.startsWith("/artifacts") },
  { href: "/artifact-types", label: "Artifact types", icon: FileType2, match: (p) => p.startsWith("/artifact-types") },
  { href: "/latex", label: "LaTeX scratch", icon: Sigma, match: (p) => p.startsWith("/latex") },
  { href: "/figures", label: "Figure scratch", icon: Shapes, match: (p) => p.startsWith("/figures") },
];

/**
 * The navigation destination list — Material 3 navigation-drawer items
 * (pill-shaped, tonal active state). Shared by the desktop drawer and the
 * mobile modal drawer; `onNavigate` lets the mobile drawer close on tap.
 */
export function NavList({
  onNavigate,
  className,
}: {
  onNavigate?: () => void;
  className?: string;
}) {
  const pathname = usePathname();
  return (
    <ul className={cn("flex flex-col gap-1", className)}>
      {NAV_ITEMS.map((item) => {
        const active = item.match(pathname);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex items-center gap-3 rounded-full px-4 py-2.5 text-[0.9rem] font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/75 hover:bg-sidebar-accent/45 hover:text-sidebar-foreground"
              )}
            >
              <Icon
                className={cn(
                  "size-5 shrink-0 transition-colors",
                  active
                    ? "text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/55 group-hover:text-sidebar-foreground"
                )}
              />
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
