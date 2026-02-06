import React from "react";
import { Sun, Moon, Monitor } from "lucide-react";

export default function ThemeSelector({ value, onChange }) {
  const options = [
    { value: "light", label: "Light", icon: Sun },
    { value: "dark", label: "Dark", icon: Moon },
    { value: "system", label: "System", icon: Monitor },
  ];

  return (
    <div className="inline-flex items-center gap-0.5 p-0.5 rounded-md bg-surface-inset border border-line">
      {options.map((option) => {
        const Icon = option.icon;
        const isActive = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`flex items-center justify-center gap-1.5 px-3 py-1 rounded text-[11px] font-medium transition-colors ${
              isActive
                ? "bg-surface-elevated text-content-primary shadow-sm"
                : "text-content-secondary hover:text-content-primary"
            }`}
          >
            <Icon size={12} strokeWidth={1.5} />
            <span>{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
