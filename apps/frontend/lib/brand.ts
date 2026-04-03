/**
 * Brand colour tokens — single source of truth for the green palette.
 * Import from here instead of hardcoding hex values or gradient strings.
 */

export const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";

export const GREEN = {
  darkest: "#24422e",
  dark: "#3a6b47",
  medium: "#509160",
  light: "#6bb97b",
  lightest: "#a0b9a8",
  muted: "#eff2f0",
} as const;
