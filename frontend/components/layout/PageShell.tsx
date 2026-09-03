// OPSpilot - frontend/components/layout/PageShell.tsx
"use client";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

interface PageShellProps {
  children: React.ReactNode;
  title?: string;
  showTabs?: boolean;
}

export function PageShell({ children, title, showTabs = false }: PageShellProps) {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col md:ml-[240px] w-full md:w-[calc(100%-240px)] min-h-screen">
        <TopBar title={title} showTabs={showTabs} />
        <main className="flex-1 p-6 space-y-6">
          {children}
        </main>
      </div>
    </div>
  );
}
