import React from "react";
import ThemeSelector from "../ThemeSelector";

export default function AppearanceTab({ values, onChange }) {
  const updateSetting = (key, value) => onChange({ ...values, [key]: value });

  const testControls = [
    { key: "test_spacing", label: "test.spacing", min: 0, max: 10, step: 1 },
    { key: "test_radius", label: "test.radius", min: 0, max: 20, step: 1 },
    { key: "test_shadow", label: "test.shadow", min: 0, max: 10, step: 1 },
    { key: "test_contrast", label: "test.contrast", min: 0, max: 100, step: 5 },
    { key: "test_brightness", label: "test.brightness", min: 0, max: 100, step: 5 },
    { key: "test_density", label: "test.density", min: 0, max: 10, step: 1 },
    { key: "test_glow", label: "test.glow", min: 0, max: 10, step: 1 },
    { key: "test_border", label: "test.border", min: 0, max: 6, step: 1 },
    { key: "test_text_scale", label: "test.text_scale", min: 80, max: 120, step: 5 },
    { key: "test_icon_scale", label: "test.icon_scale", min: 80, max: 120, step: 5 },
    { key: "test_noise", label: "test.noise", min: 0, max: 10, step: 1 },
    { key: "test_animation", label: "test.animation", min: 0, max: 10, step: 1 },
  ];

  const getValue = (key, fallback) =>
    typeof values[key] === "number" ? values[key] : fallback;

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-[11px] font-medium text-content-secondary mb-2">
          Theme
        </label>
        <ThemeSelector
          value={values.theme}
          onChange={(theme) => onChange({ ...values, theme })}
        />
      </div>
      <div className="space-y-3">
        {testControls.map((control) => (
          <div key={control.key} className="flex items-center justify-between gap-4">
            <div>
              <div className="text-[11px] font-medium text-content-primary">
                {control.label}
              </div>
              <div className="text-[10px] text-content-tertiary">
                {getValue(control.key, control.min)}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() =>
                  updateSetting(
                    control.key,
                    Math.max(
                      control.min,
                      getValue(control.key, control.min) - control.step
                    )
                  )
                }
                className="w-7 h-7 rounded border border-line text-content-secondary hover:text-content-primary hover:border-line-strong"
              >
                -
              </button>
              <button
                type="button"
                onClick={() =>
                  updateSetting(
                    control.key,
                    Math.min(
                      control.max,
                      getValue(control.key, control.min) + control.step
                    )
                  )
                }
                className="w-7 h-7 rounded border border-line text-content-secondary hover:text-content-primary hover:border-line-strong"
              >
                +
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
