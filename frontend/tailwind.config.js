/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        display: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },
      colors: {
        ink: {
          50: "#fafaf9",
          100: "#f5f5f4",
          200: "#e7e5e4",
          300: "#d6d3d1",
          400: "#a8a29e",
          500: "#78716c",
          600: "#57534e",
          700: "#44403c",
          800: "#292524",
          900: "#1c1917",
          950: "#0c0a09",
        },
      },
      boxShadow: {
        sleek: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 0 0 1px rgb(0 0 0 / 0.04)",
        card: "0 2px 12px -4px rgb(0 0 0 / 0.06), 0 0 0 1px rgb(0 0 0 / 0.04)",
      },
    },
  },
  plugins: [],
};
