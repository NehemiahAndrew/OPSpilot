// OPSpilot - frontend/components/layout/TopBar.tsx
"use client";
import { useState } from "react";

interface TopBarProps {
  title?: string;
  showTabs?: boolean;
  activeTab?: string;
  children?: React.ReactNode;
}

export function TopBar({ title, showTabs = false, activeTab = "Overview", children }: TopBarProps) {
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <header className="flex items-center justify-between h-16 px-6 bg-surface dark:bg-surface border-b border-outline-variant sticky top-0 z-40">
      <div className="flex items-center gap-6">
        {/* Mobile Menu Button */}
        <button className="md:hidden text-on-surface-variant">
          <span className="material-symbols-outlined">menu</span>
        </button>

        {/* Page Title or Tabs */}
        {showTabs ? (
          <div className="hidden md:flex gap-6">
            <a href="#" className="text-primary border-b-2 border-primary pb-1 font-medium">Overview</a>
            <a href="#" className="text-on-surface-variant hover:text-on-surface transition-colors pb-1">Requests</a>
          </div>
        ) : title ? (
          <h2 className="font-headline-md text-headline-md text-on-surface">{title}</h2>
        ) : null}
      </div>

      <div className="flex items-center gap-4">
        {/* Search */}
        <div className="relative hidden sm:block">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">search</span>
          <input
            className="bg-[#0A0A0B] border border-[#262626] rounded-lg pl-10 pr-4 py-1.5 text-body-sm focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] outline-none transition-all w-64"
            placeholder="Search operations..."
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Action Buttons */}
        <button className="text-on-surface-variant hover:text-on-surface transition-colors">
          <span className="material-symbols-outlined">notifications</span>
        </button>
        <button className="text-on-surface-variant hover:text-on-surface transition-colors">
          <span className="material-symbols-outlined">settings</span>
        </button>

        {/* User Avatar */}
        <img
          alt="User Profile"
          className="w-8 h-8 rounded-full object-cover border border-outline-variant"
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuDB3mV1WdBZP6SxoddHC0vbrHggyZqHXhmeaNl9yQTnAvqjRsUSwdp1CF_T1x9Euc8xlWsgDIGf7ruQ3DAXaecfuKmEGWpsfFVc8VZiNdbBacU6N6Nz8QTWRMoEsvuLyWI5VPnTUBPeq0-29PWujQu4nP7nflH_j4yPr8gu_y6_arBUnzWDNmaUqh4tyId2mfOchwnPZJimzynBb7x0aNG0t8AraU5WaJR5Nn7ZogvSrn8b4n8H-Ftk"
        />
      </div>

      {children}
    </header>
  );
}
