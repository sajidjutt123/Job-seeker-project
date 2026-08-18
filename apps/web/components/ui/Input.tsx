"use client";

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const FIELD_BASE =
  "w-full rounded-lg border bg-white text-ink-900 placeholder:text-ink-400 transition-colors " +
  "focus:border-brand-600 focus:ring-2 focus:ring-brand-600/15 focus:outline-none " +
  "disabled:bg-ink-100 disabled:text-ink-500 disabled:cursor-not-allowed";

function fieldClasses(hasError?: boolean, extra?: string) {
  return cn(FIELD_BASE, hasError ? "border-accent-rose" : "border-ink-300", extra);
}

interface FieldWrapperProps {
  id: string;
  label?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}

function FieldWrapper({ id, label, hint, error, required, children, className }: FieldWrapperProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-ink-800">
          {label}
          {required && <span className="ml-0.5 text-accent-rose" aria-hidden="true">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-accent-rose">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
  wrapperClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, leftIcon, rightSlot, className, wrapperClassName, id, required, ...props },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;

  return (
    <FieldWrapper id={fieldId} label={label} hint={hint} error={error} required={required} className={wrapperClassName}>
      <div className="relative">
        {leftIcon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          id={fieldId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined}
          className={fieldClasses(
            !!error,
            cn("h-11 px-3.5 text-sm", leftIcon && "pl-10", rightSlot && "pr-10", className),
          )}
          {...props}
        />
        {rightSlot && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2">{rightSlot}</span>
        )}
      </div>
    </FieldWrapper>
  );
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
  error?: string;
  options: { value: string | number; label: string }[];
  placeholder?: string;
  wrapperClassName?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, options, placeholder, className, wrapperClassName, id, required, ...props },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;

  return (
    <FieldWrapper id={fieldId} label={label} hint={hint} error={error} required={required} className={wrapperClassName}>
      <div className="relative">
        <select
          ref={ref}
          id={fieldId}
          required={required}
          aria-invalid={error ? true : undefined}
          className={fieldClasses(!!error, cn("h-11 appearance-none pl-3.5 pr-9 text-sm", className))}
          {...props}
        >
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <svg
          className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"
          viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </div>
    </FieldWrapper>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
  wrapperClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className, wrapperClassName, id, required, ...props },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;

  return (
    <FieldWrapper id={fieldId} label={label} hint={hint} error={error} required={required} className={wrapperClassName}>
      <textarea
        ref={ref}
        id={fieldId}
        required={required}
        aria-invalid={error ? true : undefined}
        className={fieldClasses(!!error, cn("min-h-24 px-3.5 py-2.5 text-sm leading-relaxed", className))}
        {...props}
      />
    </FieldWrapper>
  );
});

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  description?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, description, className, id, ...props },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;

  return (
    <div className="flex items-start gap-2.5">
      <input
        ref={ref}
        id={fieldId}
        type="checkbox"
        className={cn(
          "mt-0.5 h-4 w-4 shrink-0 rounded border-ink-300 text-brand-700 accent-brand-700",
          "focus:ring-2 focus:ring-brand-600/25 cursor-pointer",
          className,
        )}
        {...props}
      />
      <label htmlFor={fieldId} className="cursor-pointer select-none text-sm leading-tight text-ink-700">
        {label}
        {description && <span className="mt-0.5 block text-xs text-ink-500">{description}</span>}
      </label>
    </div>
  );
});
