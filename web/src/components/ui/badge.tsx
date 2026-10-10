import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 border px-2.5 py-0.5 font-mono text-[10px] tracking-[0.12em] transition-colors",
  {
    variants: {
      variant: {
        inverted: "border-white bg-white text-black font-bold",
        outline: "border-zinc-700 bg-transparent text-white",
        zinc: "border-white/10 bg-black/40 text-zinc-400",
      },
    },
    defaultVariants: { variant: "zinc" },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
