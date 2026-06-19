/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        monitor: {
          bg: "#141618",
          surface: "#1E2226",
          border: "#2A3038",
          muted: "#8B9298",
          text: "#E8EAED",
        },
        scope: {
          trace: "#3DDC84",
          dim: "#2A9D5C",
        },
        hook: {
          gold: "#F4C430",
        },
      },
      fontFamily: {
        mono: ["\"JetBrains Mono\"", "ui-monospace", "monospace"],
        sans: [
          "Segoe UI",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
      },
      boxShadow: {
        phone: "0 24px 80px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.04)",
      },
      animation: {
        "pulse-scope": "pulse-scope 2s ease-in-out infinite",
      },
      keyframes: {
        "pulse-scope": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
