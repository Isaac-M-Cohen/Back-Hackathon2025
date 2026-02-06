import React from "react";
import ThemeSelector from "../ThemeSelector";

export default function AppearanceTab({ values, onChange }) {
  const updateSetting = (key, value) => onChange({ ...values, [key]: value });

  const testControls = [
    { key: "appearance_spacing", label: "Spacing Scale", min: 0, max: 10, step: 1 },
    { key: "appearance_radius", label: "Corner Radius", min: 0, max: 20, step: 1 },
    { key: "appearance_shadow", label: "Shadow Depth", min: 0, max: 10, step: 1 },
    { key: "appearance_contrast", label: "Contrast", min: 0, max: 100, step: 5 },
    { key: "appearance_brightness", label: "Brightness", min: 0, max: 100, step: 5 },
    { key: "appearance_density", label: "UI Density", min: 0, max: 10, step: 1 },
    { key: "appearance_glow", label: "Glow Intensity", min: 0, max: 10, step: 1 },
    { key: "appearance_border", label: "Border Weight", min: 0, max: 6, step: 1 },
    { key: "appearance_text_scale", label: "Text Scale", min: 80, max: 120, step: 5 },
    { key: "appearance_icon_scale", label: "Icon Scale", min: 80, max: 120, step: 5 },
    { key: "appearance_noise", label: "Grain Amount", min: 0, max: 10, step: 1 },
    { key: "appearance_animation", label: "Motion Speed", min: 0, max: 10, step: 1 },
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
