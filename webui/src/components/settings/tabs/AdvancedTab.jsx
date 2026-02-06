import React from "react";
import SettingRow from "../SettingRow";

export default function AdvancedTab({ values, onChange }) {
  const settings = [
    {
      key: "ui_poll_interval_ms",
      label: "Poll interval",
      min: 100,
      max: 2000,
      step: 50,
      unit: "ms",
    },
    {
      key: "recognition_stable_frames",
      label: "Stable frames",
      min: 1,
      max: 30,
      step: 1,
      unit: "",
    },
    {
      key: "recognition_emit_cooldown_ms",
      label: "Emit cooldown",
      min: 0,
      max: 2000,
      step: 50,
      unit: "ms",
    },
    {
      key: "recognition_confidence_threshold",
      label: "Confidence threshold",
      min: 0,
      max: 1,
      step: 0.05,
      unit: "",
    },
  ];

  return (
    <div className="space-y-2">
      {settings.map((setting) => (
        <SettingRow
          key={setting.key}
          label={setting.label}
          value={values[setting.key]}
          unit={setting.unit}
          min={setting.min}
          max={setting.max}
          step={setting.step}
          onChange={(newValue) =>
            onChange({ ...values, [setting.key]: newValue })
          }
        />
      ))}
    </div>
  );
}
