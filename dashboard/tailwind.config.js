/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0a0a0a",
        surface: "#111111",
        border: "#222222",
        "text-primary": "#fafafa",
        "text-secondary": "#71717a",
        accent: "#22c55e",
        warning: "#eab308",
        danger: "#ef4444",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
      borderRadius: {
        card: "8px",
        button: "6px",
      },
    },
  },
  plugins: [],
}
