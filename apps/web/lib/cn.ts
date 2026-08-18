/** Minimal className joiner — avoids pulling clsx/tailwind-merge for this small a need. */
export type ClassValue = string | number | bigint | null | boolean | undefined | ClassValue[];

export function cn(...values: ClassValue[]): string {
  const out: string[] = [];
  for (const value of values) {
    if (!value) continue;
    if (Array.isArray(value)) {
      const nested = cn(...value);
      if (nested) out.push(nested);
    } else if (typeof value !== "boolean") {
      out.push(String(value));
    }
  }
  return out.join(" ");
}
