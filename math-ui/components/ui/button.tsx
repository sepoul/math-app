"use client"

import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// Material 3 buttons: pill-shaped, with hover/press feedback and elevation
// on the filled/elevated variants. Variant names kept shadcn-compatible
// (default / secondary / outline / ghost / destructive / link) so existing
// call sites don't break; `tonal` + `elevated` are the extra M3 flavours.
const buttonVariants = cva(
  "group/button relative inline-flex shrink-0 items-center justify-center gap-2 rounded-full border border-transparent text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:ring-[3px] focus-visible:ring-ring/60 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40 aria-invalid:ring-destructive/30 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-[1.15rem]",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-e1 hover:shadow-e2 hover:brightness-110 active:brightness-95",
        tonal:
          "bg-secondary text-secondary-foreground hover:brightness-[0.97] active:brightness-95",
        secondary:
          "bg-secondary text-secondary-foreground hover:brightness-[0.97] active:brightness-95",
        elevated:
          "bg-card text-foreground shadow-e1 hover:shadow-e2 hover:bg-accent",
        outline:
          "border-border bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground",
        ghost:
          "bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground",
        destructive:
          "bg-destructive text-destructive-foreground shadow-e1 hover:shadow-e2 hover:brightness-110",
        link: "rounded-none text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-5 has-[>svg:first-child]:pl-4",
        xs: "h-7 px-3 text-xs [&_svg:not([class*='size-'])]:size-3.5",
        sm: "h-8 px-4 text-[0.8rem] [&_svg:not([class*='size-'])]:size-4",
        lg: "h-12 px-7 text-[0.95rem]",
        icon: "size-10",
        "icon-xs": "size-7 [&_svg:not([class*='size-'])]:size-4",
        "icon-sm": "size-8",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
