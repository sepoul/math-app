import Link from "next/link";
import { Sigma } from "lucide-react";
import { cn } from "@/lib/utils";

/** App wordmark — a tonal logo chip + name. Links home. */
export function Brand({
  onClick,
  className,
}: {
  onClick?: () => void;
  className?: string;
}) {
  return (
    <Link
      href="/"
      onClick={onClick}
      className={cn(
        "flex items-center gap-2.5 font-heading text-[0.95rem] font-semibold tracking-tight text-foreground transition-opacity hover:opacity-80",
        className
      )}
    >
      <span className="flex size-8 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-e1">
        <Sigma className="size-[1.1rem]" />
      </span>
      Math AI
    </Link>
  );
}
