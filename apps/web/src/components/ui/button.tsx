import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "sm";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-control font-medium whitespace-nowrap " +
  "transition-[background-color,color,border-color] duration-150 ease-standard " +
  "disabled:cursor-not-allowed disabled:border-dashed [&_svg]:size-4 [&_svg]:shrink-0";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-mint text-canvas hover:bg-mint-strong disabled:bg-inset disabled:text-ink-muted disabled:border disabled:border-line",
  secondary:
    "border border-line-strong text-ink hover:bg-inset disabled:text-ink-muted disabled:border-line disabled:hover:bg-transparent",
  ghost: "text-ink-muted hover:bg-inset hover:text-ink disabled:hover:bg-transparent",
  danger: "border border-negative text-negative hover:bg-inset",
};

const SIZES: Record<Size, string> = {
  md: "min-h-12 px-5 text-body",
  sm: "min-h-10 px-3 text-small",
};

interface StyleProps {
  variant?: Variant | undefined;
  size?: Size | undefined;
}

export function buttonClasses({ variant = "primary", size = "md" }: StyleProps = {}): string {
  return cn(BASE, VARIANTS[variant], SIZES[size]);
}

export type ButtonProps = ComponentProps<"button"> & StyleProps;

export function Button({ variant, size, className, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonClasses({ variant, size }), className)} {...props} />
  );
}

interface ButtonLinkProps extends StyleProps {
  href: string;
  children: ReactNode;
  className?: string;
}

/** A link that looks like a button. Use it for navigation, Button for actions. */
export function ButtonLink({ href, variant, size, className, children }: ButtonLinkProps) {
  return (
    <Link href={href} className={cn(buttonClasses({ variant, size }), className)}>
      {children}
    </Link>
  );
}
