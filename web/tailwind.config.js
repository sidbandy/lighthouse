/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // A lighthouse: a white tower, a navy sea, one warm light. Three
        // colours, used in that order of quantity — most of the screen is
        // paper, structure and type are navy, and the beacon is spent only on
        // the single thing that matters in a given view.
        //
        // One ramp for everything structural, ordered the conventional way:
        // low numbers are light fills and borders, high numbers are type.
        // Keep it monotonic.
        navy: {
          50: "#f1f5f9",
          100: "#e3eaf1",
          200: "#cbd7e3",
          300: "#a6bacd",
          400: "#7893ad",
          500: "#56738f",
          600: "#3d5a75",
          700: "#2a4359",
          800: "#1a2f42",
          900: "#0e1e2d",
        },
        // The light itself. Reserved for the primary action, the live figure,
        // and the one row worth looking at first — never for decoration.
        beacon: {
          100: "#fdecd8",
          300: "#f9bd77",
          400: "#f5a24a",
          500: "#ef8420",
          600: "#cc6710", // the text-safe step: ~4.4:1 on white
          700: "#a44f09",
          glow: "rgba(239, 132, 32, 0.10)",
        },
        // The page: warm cream, not white. Chart paper rather than a screen —
        // it takes the glare off a tool meant to be stared at for hours, and it
        // is what makes the navy read as ink and the beacon as lamplight. Cards
        // sit on top in white and lift by a hair.
        paper: "#faf7f0",
        // Lane accents — distinct at a glance, all dark enough to read as type.
        reach: "#6d28d9",
        target: "#0f766e",
        safety: "#0369a1",
        // Semantic, at text weight rather than the pastel tints a dark
        // background could afford.
        good: "#15803d",
        warn: "#b45309",
        bad: "#b91c1c",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      // Numeric weights, matching the Inter weights actually loaded in
      // index.css and the numeric convention the rest of these tokens use.
      // They were referenced throughout the components before being defined
      // here, and an undefined utility is silently dropped rather than
      // erroring — so nothing on the page was ever actually bold.
      fontWeight: {
        400: "400",
        450: "450",
        500: "500",
        600: "600",
        700: "700",
      },
      borderRadius: {
        xl: "0.875rem",
      },
      // Tinted with the navy rather than neutral black, so shadows read as
      // depth in the same light the rest of the palette lives in.
      boxShadow: {
        card: "0 1px 2px rgba(14,30,45,0.04), 0 1px 3px rgba(14,30,45,0.06)",
        lift: "0 8px 24px rgba(14,30,45,0.12), 0 2px 6px rgba(14,30,45,0.06)",
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
