import Link from "next/link";
import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Clickable card — Material 3 surface that lifts on hover. The whole
 * surface is the link target. `chevron={false}` drops the trailing
 * affordance for dense rows.
 */
export function LinkCard({
  href,
  children,
  chevron = true,
  contentClassName,
}: {
  href: string;
  children: ReactNode;
  chevron?: boolean;
  contentClassName?: string;
}) {
  return (
    <Link href={href} className="group block">
      <Card className="transition-all duration-150 group-hover:-translate-y-0.5 group-hover:shadow-e3">
        <CardContent
          className={cn("flex items-center gap-3 px-5 py-4", contentClassName)}
        >
          <div className="min-w-0 flex-1">{children}</div>
          {chevron && (
            <ChevronRight className="size-5 shrink-0 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
