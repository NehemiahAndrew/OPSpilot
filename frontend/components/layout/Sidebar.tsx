// OPSpilot - frontend/components/layout/Sidebar.tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: "dashboard", activeIcon: "dashboard" },
  { href: "/requests", label: "Requests", icon: "list_alt" },
  { href: "/runs", label: "Agent Runs", icon: "smart_toy" },
  { href: "/approvals", label: "Approvals", icon: "verified_user" },
  { href: "/evidence", label: "Evidence", icon: "fact_check" },
  { href: "/evaluation", label: "Evaluations", icon: "analytics" },
  { href: "/improvement", label: "Improvement", icon: "trending_up" },
  { href: "/audit", label: "Audit Log", icon: "history" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="hidden md:flex flex-col w-[240px] h-screen fixed left-0 top-0 bg-surface-container dark:bg-surface-container border-r border-outline-variant p-6 text-primary dark:text-primary z-50">
      {/* Brand */}
      <div className="flex items-center gap-3 mb-8">
        <div className="w-8 h-8 rounded bg-primary flex items-center justify-center text-on-primary font-bold">O</div>
        <div>
          <h1 className="font-display text-headline-md font-semibold text-on-surface">OpsPilot</h1>
          <p className="font-label-caps text-label-caps text-on-surface-variant">Agentic Workforce</p>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-200",
                isActive
                  ? "text-primary font-bold bg-secondary-container"
                  : "text-on-surface-variant font-medium hover:bg-surface-variant"
              )}
            >
              <span
                className="material-symbols-outlined"
                style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </div>

      {/* Footer */}
      <div className="mt-auto space-y-4 pt-4">
        <button className="w-full py-2 bg-[#6366F1] text-white rounded-lg font-medium hover:bg-opacity-90 transition-opacity">
          Hackathon Demo
        </button>
        <div className="flex items-center gap-3 px-3 py-2 text-on-surface-variant font-medium">
          <span className="material-symbols-outlined">cloud_done</span>
          System Status
        </div>
      </div>
    </nav>
  );
}
