import React from "react";
import NumericStepper from "./NumericStepper";

export default function SettingRow({ label, value, unit, min, max, step, onChange }) {
  return (
    <div className="flex items-center justify-between py-1">
      <div className="text-[11px] text-content-secondary">{label}</div>
      <NumericStepper
        value={value}
        onChange={onChange}
        min={min}
        max={max}
        step={step}
        unit={unit}
      />
    </div>
  );
}
