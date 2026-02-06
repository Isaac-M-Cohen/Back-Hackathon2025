import React, { useState, useEffect } from "react";

function DeviceSelectSegmented({ label, value, devices, onChange }) {
  const [showPicker, setShowPicker] = useState(false);
  const [mode, setMode] = useState(
    value === "" || value === null ? "default" : "pick"
  );
  const isDefault = value === "" || value === null;
  const selected = devices.find((device) => device.index === value);

  useEffect(() => {
    setMode(isDefault ? "default" : "pick");
    if (isDefault) {
      setShowPicker(false);
    }
  }, [isDefault]);

  return (
    <div>
      <label className="block text-[11px] text-content-secondary mb-1.5">{label}</label>
      <div className="rounded border border-line bg-surface-inset p-1.5 text-[11px]">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              setMode("default");
              setShowPicker(false);
              onChange(null);
            }}
            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
              mode === "default"
                ? "bg-chip-active text-chip-active-text"
                : "bg-chip-idle text-chip-idle-text hover:bg-chip-idle-hover"
            }`}
          >
            Default
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("pick");
              setShowPicker(true);
            }}
            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
              mode === "pick"
                ? "bg-chip-active text-chip-active-text"
                : "bg-chip-idle text-chip-idle-text hover:bg-chip-idle-hover"
            }`}
          >
            Pick
          </button>
          <span className="text-[10px] text-content-tertiary truncate">
            {selected ? selected.name : "System default"}
          </span>
        </div>
        {(showPicker || mode === "pick") && (
          <div className="mt-1.5 max-h-20 overflow-y-auto grid grid-cols-1 gap-0.5">
            {devices.map((device) => (
              <button
                key={device.index}
                type="button"
                onClick={() => {
                  onChange(Number(device.index));
                  setShowPicker(false);
                  setMode("pick");
                }}
                className={`w-full text-left px-1.5 py-0.5 rounded text-[10px] transition-colors ${
                  device.index === value
                    ? "bg-surface-elevated text-content-primary"
                    : "hover:bg-surface-base text-content-secondary"
                }`}
              >
                {device.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function IOTab({ values, onChange, audioDevices }) {
  const micValue = values.microphone_device_index ?? null;
  const speakerValue = values.speaker_device_index ?? null;
  const inputDevices = audioDevices?.inputs || [];
  const outputDevices = audioDevices?.outputs || [];

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[10px] font-medium text-content-tertiary uppercase tracking-wide mb-2">
          Audio I/O
        </h3>
        <div className="space-y-2">
          <DeviceSelectSegmented
            label="Microphone"
            value={micValue}
            devices={inputDevices}
            onChange={(value) =>
              onChange({
                ...values,
                microphone_device_index: value,
              })
            }
          />
          <DeviceSelectSegmented
            label="Speaker"
            value={speakerValue}
            devices={outputDevices}
            onChange={(value) =>
              onChange({
                ...values,
                speaker_device_index: value,
              })
            }
          />
        </div>
      </div>
    </div>
  );
}
