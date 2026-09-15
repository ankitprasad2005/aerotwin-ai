import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        black: "#000000",
        surface: "#111111",
        "surface-raised": "#1A1A1A",
        border: "#222222",
        "border-visible": "#333333",
        "text-disabled": "#666666",
        "text-secondary": "#999999",
        "text-primary": "#E8E8E8",
        "text-display": "#FFFFFF",
        accent: "#D71921",
        "accent-subtle": "rgba(215,25,33,0.15)",
        success: "#4A9E5C",
        warning: "#D4A843",
        interactive: "#5B9BF6",
      },
      fontFamily: {
        display: ["Doto", "Space Mono", "monospace"],
        body: ["Space Grotesk", "DM Sans", "system-ui", "sans-serif"],
        mono: ["Space Mono", "JetBrains Mono", "SF Mono", "monospace"],
      },
      // `text-body` / `text-body-sm` are used throughout the UI; without these entries
      // Tailwind silently generates no CSS for them and text falls back to the default size.
      fontSize: {
        body: ["16px", { lineHeight: "1.5" }],
        "body-sm": ["14px", { lineHeight: "1.5" }],
      },
      spacing: {
        "2xs": "2px",
        xs: "4px",
        sm: "8px",
        md: "16px",
        lg: "24px",
        xl: "32px",
        "2xl": "48px",
        "3xl": "64px",
        "4xl": "96px",
      },
    },
  },
  plugins: [],
} satisfies Config;
