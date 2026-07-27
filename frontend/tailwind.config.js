/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      colors: {
        // The project palette, used verbatim. Everything else in the UI is one
        // of these five colours or a translucent tint of navy, so the interface
        // never drifts outside the brief.
        navy: '#001F3F',
        pink: '#D81B60',
        amber: '#FFC107',

        // Navy tints for surfaces, borders and secondary text. Defined as solid
        // hex rather than opacity utilities so they composite predictably over
        // the white background and stay readable when printed.
        ink: {
          900: '#001F3F',
          700: '#1A3551',
          600: '#2E4A66',
          500: '#4A657D',
          400: '#7A8FA3',
          300: '#AEBECC',
          200: '#D6DEE6',
          100: '#EAEFF4',
          50: '#F5F8FA',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(0, 31, 63, 0.06), 0 4px 12px rgba(0, 31, 63, 0.05)',
      },
    },
  },
  plugins: [],
};
