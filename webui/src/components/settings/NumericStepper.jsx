import React from "react";

export default function NumericStepper({ value, onChange, min, max, step, unit = "" }) {
  const handleDecrement = () => {
    const next = Math.max(min, value - step);
    onChange(next);
  };

  const handleIncrement = () => {
    const next = Math.min(max, value + step);
    onChange(next);
  };

  const formatValue = (val) => {
    if (Number.isInteger(step)) {
      return val.toString();
    }
    return val.toFixed(2);
  };

  return (
    <div className="flex items-center gap-1 rounded border border-line bg-surface-inset px-1 py-0.5">
      <button
        type="button"
        onClick={handleDecrement}
        disabled={value <= min}
        className="w-4 h-4 rounded text-[10px] text-content-secondary hover:text-content-primary hover:bg-surface-base transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
      >
        −
      </button>
      <span className="min-w-[40px] text-center text-[10px] text-content-primary tabular-nums">
        {formatValue(value)}{unit && ` ${unit}`}
      </span>
      <button
        type="button"
        onClick={handleIncrement}
        disabled={value >= max}
        className="w-4 h-4 rounded text-[10px] text-content-secondary hover:text-content-primary hover:bg-surface-base transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
      >
        +
      </button>
    </div>
  );
}
