import * as React from "react";

import { cn } from "@/lib/utils";

const fieldClass =
  "w-full rounded-md border border-line-strong bg-raised px-2.5 text-xs text-fg placeholder:text-fg-subtle transition-colors hover:border-[#3d3d47] focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/20";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input ref={ref} type={type} className={cn(fieldClass, "h-7", className)} {...props} />
  ),
);
Input.displayName = "Input";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(fieldClass, "min-h-16 resize-y py-2 leading-relaxed", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";

interface FieldProps {
  label: React.ReactNode;
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/** Label + control + optional hint/error, stacked. */
function Field({ label, htmlFor, hint, error, className, children }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-2xs font-medium text-fg-muted">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-2xs text-danger">
          {error}
        </p>
      ) : (
        hint && <p className="text-2xs text-fg-subtle">{hint}</p>
      )}
    </div>
  );
}

export { Input, Textarea, Field };
