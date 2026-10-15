import type { Config } from "tailwindcss";

// Dark, data-dense "ops console" theme. Colours here are the single source of truth for the UI;
// chart components use the same hex values through CSS variables (src/index.css).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0b0e14",
        panel: "#11161f",
        "panel-raised": "#171e2b",
        line: "#1f2733",
        "line-strong": "#2d3748",
        ink: "#d8dee9",
        "ink-strong": "#f1f5f9",
        muted: "#7d8590",
        faint: "#4b5563",
        accent: "#38bdf8",
        "accent-subtle": "rgba(56,189,248,0.12)",
        ok: "#22c55e",
        warn: "#f59e0b",
        bad: "#ef4444",
      },
      fontFamily: {
        // System stacks only: the app must not make external font requests.
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px" }],
        xs: ["11px", { lineHeight: "16px" }],
        sm: ["12px", { lineHeight: "18px" }],
        base: ["13px", { lineHeight: "20px" }],
        lg: ["15px", { lineHeight: "22px" }],
        xl: ["18px", { lineHeight: "26px" }],
        "2xl": ["22px", { lineHeight: "28px" }],
      },
      // Dense spacing aliases (the default numeric scale still works alongside them).
      spacing: {
        "2xs": "2px",
        xs: "4px",
        sm: "6px",
        md: "10px",
        lg: "14px",
        xl: "20px",
        "2xl": "28px",
      },
    },
  },
  plugins: [],
} satisfies Config;
