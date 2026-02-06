import React from "react";
import { Palette, Sliders, Settings } from "lucide-react";

export default function TabSidebar({ currentTab, onTabChange }) {
  const tabs = [
    { id: "appearance", label: "Appearance", icon: Palette },
    { id: "io", label: "I/O", icon: Sliders },
    { id: "advanced", label: "Advanced", icon: Settings },
    { id: "test-1", label: "test.tab_1", icon: Settings },
    { id: "test-2", label: "test.tab_2", icon: Settings },
    { id: "test-3", label: "test.tab_3", icon: Settings },
    { id: "test-4", label: "test.tab_4", icon: Settings },
    { id: "test-5", label: "test.tab_5", icon: Settings },
    { id: "test-6", label: "test.tab_6", icon: Settings },
    { id: "test-7", label: "test.tab_7", icon: Settings },
    { id: "test-8", label: "test.tab_8", icon: Settings },
  ];

  return (
    <div className="flex flex-col gap-0.5 min-w-[100px]">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = currentTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onTabChange(tab.id)}
            className={`flex items-center gap-2 px-2.5 py-1.5 rounded text-[11px] font-medium transition-colors text-left ${
              isActive
                ? "bg-surface-elevated text-content-primary"
                : "text-content-secondary hover:text-content-primary"
            }`}
          >
            <Icon size={13} strokeWidth={1.5} />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
