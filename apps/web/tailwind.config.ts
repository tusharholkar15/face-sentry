import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#080c14",
        surface: "#0f172a",
        "surface-elevated": "#1e293b",
        "surface-card": "rgba(15, 23, 42, 0.75)",
        primary: {
          DEFAULT: "#00f0ff",
          foreground: "#030712",
          50: "#e0fcff",
          500: "#00f0ff",
          600: "#00c8d6",
        },
        accent: {
          DEFAULT: "#38bdf8",
          foreground: "#030712",
        },
        border: "rgba(255, 255, 255, 0.1)",
        ring: "#00f0ff",
        status: {
          active: "#10b981",
          warning: "#f59e0b",
          danger: "#ef4444",
          idle: "#64748b",
        }
      },
      backdropBlur: {
        xs: "2px",
      },
      fontFamily: {
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
