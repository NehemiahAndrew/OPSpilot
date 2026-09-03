import type { Config } from "tailwindcss";

/**
 * OPSpilot design tokens.
 * SOURCE OF TRUTH: docs/STITCH_INVENTORY.md sections 3 (colors), 4 (typography)
 * and the spacing/radius tokens in the Stitch Tailwind config.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./services/**/*.{ts,tsx}",
    "./types/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Material-3 dark palette (from STITCH_INVENTORY.md 3a)
        background: "#131314",
        "on-background": "#e5e2e3",
        surface: "#131314",
        "on-surface": "#e5e2e3",
        "surface-bright": "#3a393a",
        "surface-dim": "#131314",
        "surface-variant": "#353436",
        "on-surface-variant": "#c7c4d7",
        "surface-container-lowest": "#0e0e0f",
        "surface-container-low": "#1c1b1c",
        "surface-container": "#201f20",
        "surface-container-high": "#2a2a2b",
        "surface-container-highest": "#353436",
        "surface-tint": "#c0c1ff",
        "inverse-surface": "#e5e2e3",
        "inverse-on-surface": "#313031",
        primary: "#c0c1ff",
        "on-primary": "#1000a9",
        "primary-container": "#8083ff",
        "on-primary-container": "#0d0096",
        "primary-fixed": "#e1e0ff",
        "on-primary-fixed": "#07006c",
        "primary-fixed-dim": "#c0c1ff",
        "on-primary-fixed-variant": "#2f2ebe",
        "inverse-primary": "#494bd6",
        secondary: "#b9c8de",
        "on-secondary": "#233143",
        "secondary-container": "#39485a",
        "on-secondary-container": "#a7b6cc",
        "secondary-fixed": "#d4e4fa",
        "on-secondary-fixed": "#0d1c2d",
        "secondary-fixed-dim": "#b9c8de",
        "on-secondary-fixed-variant": "#39485a",
        tertiary: "#ffb783",
        "on-tertiary": "#4f2500",
        "tertiary-container": "#d97721",
        "on-tertiary-container": "#452000",
        "tertiary-fixed": "#ffdcc5",
        "on-tertiary-fixed": "#301400",
        "tertiary-fixed-dim": "#ffb783",
        "on-tertiary-fixed-variant": "#703700",
        error: "#ffb4ab",
        "on-error": "#690005",
        "error-container": "#93000a",
        "on-error-container": "#ffdad6",
        outline: "#908fa0",
        "outline-variant": "#464554",
        // Ad-hoc brand colors (STITCH_INVENTORY.md 3b)
        brand: {
          indigo: "#6366F1",
          input: "#0A0A0B",
          card: "#141415",
          edge: "#262626",
          slate: "#94A3B8",
        },
      },
            fontFamily: {
        // STITCH_INVENTORY.md 4
        display: ["Geist", "sans-serif"],
        "headline-lg": ["Geist", "sans-serif"],
        "headline-md": ["Geist", "sans-serif"],
        "body-lg": ["Inter", "sans-serif"],
        "body-md": ["Inter", "sans-serif"],
        "body-sm": ["Inter", "sans-serif"],
        "code-md": ["JetBrains Mono", "monospace"],
        "label-caps": ["JetBrains Mono", "monospace"],
      },
      fontSize: {
        display: ["32px", { lineHeight: "40px", letterSpacing: "-0.02em", fontWeight: "600" }],
        "headline-lg": ["24px", { lineHeight: "32px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "headline-md": ["20px", { lineHeight: "28px", fontWeight: "500" }],
        "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "body-sm": ["12px", { lineHeight: "18px", fontWeight: "400" }],
        "code-md": ["13px", { lineHeight: "20px", fontWeight: "400" }],
        "label-caps": ["11px", { lineHeight: "16px", letterSpacing: "0.05em", fontWeight: "600" }],
      },
      spacing: {
        sidebar_width: "240px",
        unit: "8px",
        stack_sm: "8px",
        stack_md: "16px",
        stack_lg: "24px",
        container_padding: "24px",
        gutter: "16px",
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
        full: "9999px",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;