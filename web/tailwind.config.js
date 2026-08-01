/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Cool slate base — a calm, focused workspace rather than stark black.
        ink: {
          950: "#0a0e16",
          900: "#0f1420",
          850: "#141b2b",
          800: "#1a2233",
          700: "#242f45",
          600: "#33415e",
          500: "#475571",
        },
        // Text ramp, brightest to quietest. 500/600 were used throughout the
        // components before they existed here, which silently fell through to
        // the inherited body colour — so the text meant to be quietest rendered
        // *brighter* than the tier above it. They are defined now; keep the
        // ramp monotonic if it ever grows again.
        mist: {
          600: "#57617a",
          500: "#6b7791",
          400: "#7c8aa5",
          300: "#9aa7bf",
          200: "#c3ccdb",
          100: "#e4e9f1",
        },
        // The beacon: a warm signal against the cool base. Used sparingly, for
        // the thing that matters on a screen.
        beacon: {
          600: "#d98a1f",
          500: "#f0a52e",
          400: "#f6bd5c",
          glow: "rgba(240, 165, 46, 0.14)",
        },
        // Lane accents — distinct but not loud.
        reach: "#c084fc",
        target: "#5eead4",
        safety: "#7dd3fc",
        // Semantic.
        good: "#4ade80",
        warn: "#fbbf24",
        bad: "#f87171",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        xl: "0.875rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.15)",
        lift: "0 8px 24px rgba(0,0,0,0.35)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        sweep: {
          "0%, 100%": { opacity: "0.3" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out",
        sweep: "sweep 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
