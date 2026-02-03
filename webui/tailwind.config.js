/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          base:             'var(--color-bg-base)',
          elevated:         'var(--color-bg-elevated)',
          inset:            'var(--color-bg-inset)',
          input:            'var(--color-bg-input)',
          'base-hover':     'var(--color-bg-base-hover)',
          'elevated-hover': 'var(--color-bg-elevated-hover)',
          'inset-hover':    'var(--color-bg-inset-hover)',
        },
        content: {
          primary:   'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          tertiary:  'var(--color-text-tertiary)',
          onaccent:  'var(--color-text-on-accent)',
        },
        line: {
          DEFAULT: 'var(--color-border)',
          strong:  'var(--color-border-strong)',
          divider: 'var(--color-divider)',
        },
        accent: {
          DEFAULT: 'var(--color-accent)',
          hover:   'var(--color-accent-hover)',
        },
        btn: {
          secondary:        'var(--color-btn-secondary)',
          'secondary-hover':'var(--color-btn-secondary-hover)',
          'secondary-text': 'var(--color-btn-secondary-text)',
          tertiary:         'var(--color-btn-tertiary)',
          'tertiary-hover': 'var(--color-btn-tertiary-hover)',
          'tertiary-text':  'var(--color-btn-tertiary-text)',
        },
        chip: {
          active:       'var(--color-chip-active)',
          'active-text':'var(--color-chip-active-text)',
          idle:         'var(--color-chip-idle)',
          'idle-text':  'var(--color-chip-idle-text)',
          'idle-hover': 'var(--color-chip-idle-hover)',
        },
        toggle: {
          on:   'var(--color-toggle-on)',
          off:  'var(--color-toggle-off)',
          knob: 'var(--color-toggle-knob)',
        },
        stepper: {
          bg:    'var(--color-stepper-bg)',
          hover: 'var(--color-stepper-hover)',
          text:  'var(--color-stepper-text)',
        },
      },
    },
  },
  plugins: [],
};
