/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./templates/**/*.html",
        "./templates/**/**/*.html",
    ],
    theme: {
        extend: {
            fontFamily: {
                display: ["Space Grotesk", "Inter", "sans-serif"],
                body: ["Inter", "system-ui", "sans-serif"],
            },
            colors: {
                brand: {
                    50: "#ecfeff",
                    100: "#cffafe",
                    200: "#a5f3fc",
                    300: "#67e8f9",
                    400: "#22d3ee",
                    500: "#0ea5e9",
                    600: "#0284c7",
                    700: "#0369a1",
                    800: "#075985",
                    900: "#0c4a6e",
                },
            },
            boxShadow: {
                card: "0 20px 45px -20px rgba(15, 23, 42, 0.65)",
            },
        },
    },
    plugins: [require("@tailwindcss/forms"), require("@tailwindcss/typography")],
};
