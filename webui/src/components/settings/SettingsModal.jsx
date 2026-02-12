import React, { useEffect, useRef, useState } from "react";
import TabSidebar from "./TabSidebar";
import AppearanceTab from "./tabs/AppearanceTab";
import IOTab from "./tabs/IOTab";
import AdvancedTab from "./tabs/AdvancedTab";

export default function SettingsModal({
  isOpen,
  values,
  onChange,
  onSave,
  onClose,
  onReset,
  audioDevices,
  variant = "modal",
}) {
  const [currentTab, setCurrentTab] = useState("appearance");
  const [ready, setReady] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    timerRef.current = setTimeout(() => {
      setReady(true);
    }, 450);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const shouldListen = variant === "window" || isOpen;
    if (!shouldListen) {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.isComposing) {
        return;
      }
      if (variant !== "window" && !ready) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        onSave();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, onSave, ready, variant]);

  const handleCancel = (event) => {
    event.stopPropagation();
    if (!ready) return;
    console.log("[Settings] cancel clicked");
    onClose();
  };

  const handleReset = (event) => {
    event.stopPropagation();
    if (!ready) return;
    console.log("[Settings] reset clicked");
    onReset();
  };

  const handleSave = (event) => {
    event.stopPropagation();
    if (!ready) return;
    console.log("[Settings] save clicked");
    onSave();
  };

  const content = (
    <div
      className="bg-surface-elevated rounded-xl shadow-lg border border-line w-[480px] h-[340px] flex flex-col overflow-hidden"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="flex-1 flex overflow-hidden">
        <div className="w-40 border-r border-line flex flex-col">
          <div className="flex-1 overflow-y-auto py-2.5 px-2">
            <TabSidebar currentTab={currentTab} onTabChange={setCurrentTab} />
          </div>
        </div>

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {currentTab === "appearance" && (
              <AppearanceTab values={values} onChange={onChange} />
            )}
            {currentTab === "io" && (
              <IOTab
                values={values}
                onChange={onChange}
                audioDevices={audioDevices}
              />
            )}
            {currentTab === "advanced" && (
              <AdvancedTab values={values} onChange={onChange} />
            )}
          </div>

          <div className="border-t border-line px-4 py-2.5 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="px-2.5 py-1 text-[11px] rounded text-content-tertiary hover:text-content-secondary transition-colors"
            >
              Reset to defaults
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="px-2.5 py-1 text-[11px] rounded text-content-secondary hover:text-content-primary transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="px-3 py-1 text-[11px] rounded bg-accent text-content-onaccent hover:bg-accent-hover transition-colors"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  if (variant === "window") {
    return (
      <div className="h-full bg-surface-elevated flex flex-col overflow-hidden">
        <div className="flex-1 flex overflow-hidden">
          <div className="w-44 border-r border-line flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto py-2.5 px-2">
              <TabSidebar currentTab={currentTab} onTabChange={setCurrentTab} />
            </div>
          </div>
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
            <div className="flex-1 overflow-y-auto px-4 py-3">
              {currentTab === "appearance" && (
                <AppearanceTab values={values} onChange={onChange} />
              )}
              {currentTab === "io" && (
                <IOTab
                  values={values}
                  onChange={onChange}
                  audioDevices={audioDevices}
                />
              )}
              {currentTab === "advanced" && (
                <AdvancedTab values={values} onChange={onChange} />
              )}
            </div>
            <div className="border-t border-line px-4 py-2.5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={handleReset}
                className="px-2.5 py-1 text-[11px] rounded text-content-tertiary hover:text-content-secondary transition-colors"
              >
                Reset to defaults
              </button>
              <button
                type="button"
                onClick={handleCancel}
                className="px-2.5 py-1 text-[11px] rounded text-content-secondary hover:text-content-primary transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                className="px-3 py-1 text-[11px] rounded bg-accent text-content-onaccent hover:bg-accent-hover transition-colors"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className={`fixed inset-0 bg-black/20 flex items-center justify-center p-6 z-50 ${ready ? "" : "pointer-events-none"}`}
    >
      {content}
    </div>
  );
}
