// Reusable UI primitives — presentational, no business logic, no store access.
// Flexible and embeddable so pages compose them however they need.
// Backed by the shadcn/ui component library.

import type { ReactNode } from "react";
import { Button as ShadcnButton } from "@/components/ui/button";
import { Input as ShadcnInput } from "@/components/ui/input";
import { Badge as ShadcnBadge } from "@/components/ui/badge";
import {
  Select as ShadcnSelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label as ShadcnLabel } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  style,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  type?: "button" | "submit";
  style?: React.CSSProperties;
  title?: string;
}) {
  const shadcnVariant =
    variant === "primary"
      ? "default"
      : variant === "secondary"
        ? "secondary"
        : variant === "danger"
          ? "destructive"
          : "ghost";
  return (
    <ShadcnButton
      type={type}
      variant={shadcnVariant}
      onClick={onClick}
      disabled={disabled}
      style={style}
      title={title}
    >
      {children}
    </ShadcnButton>
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
  autoFocus,
  onEscape,
  style,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  onEscape?: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <ShadcnInput
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Escape") onEscape?.();
      }}
      placeholder={placeholder}
      autoFocus={autoFocus}
      style={style}
    />
  );
}

export function Select<T extends string | number>({
  value,
  onChange,
  options,
  placeholder,
  style,
}: {
  value: T | null;
  onChange: (v: T | null) => void;
  options: { value: T; label: string }[];
  placeholder?: string;
  style?: React.CSSProperties;
}) {
  const current = value == null ? undefined : String(value);
  return (
    <ShadcnSelect
      value={current}
      onValueChange={(v) => onChange(v === "" ? null : (v as unknown as T))}
    >
      <SelectTrigger style={style} className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={String(o.value)} value={String(o.value)}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </ShadcnSelect>
  );
}

export function Badge({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "accent" | "green" | "red";
}) {
  const variant =
    tone === "red"
      ? "destructive"
      : tone === "accent"
        ? "secondary"
        : tone === "green"
          ? "outline"
          : "secondary";
  const extra =
    tone === "green"
      ? "border-green/50 text-green"
      : tone === "accent"
        ? "border-accent/40 text-accent"
        : tone === "muted"
          ? "text-subtext"
          : "";
  return (
    <ShadcnBadge variant={variant} className={cn(extra)}>
      {children}
    </ShadcnBadge>
  );
}

export function List({
  children,
  gap = 6,
}: {
  children: ReactNode;
  gap?: number;
}) {
  return (
    <ul
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap,
      }}
    >
      {children}
    </ul>
  );
}

export function ListItem({
  children,
  style,
}: {
  children: ReactNode;
  style?: React.CSSProperties;
}) {
  return <li style={style}>{children}</li>;
}

export function Field({
  label,
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {label && (
        <ShadcnLabel style={{ fontSize: "0.8rem", color: "var(--subtext)" }}>
          {label}
        </ShadcnLabel>
      )}
      {children}
    </div>
  );
}
