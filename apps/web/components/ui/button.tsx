import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-academic-accent focus-visible:ring-offset-2 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-academic-navy text-white shadow-sm hover:bg-academic-slate",
        gold: "bg-academic-navy text-white shadow-sm hover:bg-academic-slate",
        teal: "bg-academic-accent text-white shadow-sm hover:bg-blue-700",
        soft: "border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 hover:text-academic-navy",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        dangerOutline:
          "border border-red-300 bg-red-50 text-red-700 hover:border-red-400 hover:bg-red-100",
        outline:
          "border border-slate-200 bg-white text-slate-700 hover:border-academic-accent/40 hover:bg-academic-accent-soft hover:text-academic-navy",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "text-slate-600 hover:bg-slate-100 hover:text-academic-navy",
        link: "text-academic-accent underline-offset-4 hover:text-blue-700 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
