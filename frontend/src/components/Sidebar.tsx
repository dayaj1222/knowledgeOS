import { NavLink } from "react-router-dom";
import { useState } from "react";
import {
  BookOpen,
  CalendarDays,
  Settings,
  Bot,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { USER_ID } from "../api";
import ThemeToggle from "./ThemeToggle";

const items = [
  { to: "/", label: "Tutor", icon: Bot },
  { to: "/library", label: "Library & Docs", icon: BookOpen },
  { to: "/plan", label: "Study Schedule", icon: CalendarDays },
  { to: "/settings", label: "Preferences", icon: Settings },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  function toggleCollapse() {
    setCollapsed(!collapsed);
  }

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      {/* Brand Header — fixed width wrapper */}
      <div className="fixed-width-col">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <img src="/favicon.svg" alt="KnowlegeOS" width={22} height={22} />
          </div>
          <div className="sidebar-brand-text">
            <span className="font-bold text-base leading-tight tracking-tight text-foreground flex items-center gap-1.5">
              Knowlege<span className="text-accent">OS</span>
            </span>
            <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">
              Adaptive Study
            </span>
          </div>
        </div>
      </div>

      {/* Navigation icons — fixed width container */}
      <div className="fixed-width-col nav-col">
        <nav className="sidebar-nav">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
              title={collapsed ? label : undefined}
            >
            <Icon size={18} strokeWidth={2} />
            <span className="nav-label">
              {label}
            </span>
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Theme + collapse */}
      <div className="fixed-width-col">
        <div className="pt-3 pb-2 border-t border-border space-y-1.5">
          <ThemeToggle compact collapsed={collapsed} />
          <button
            onClick={toggleCollapse}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex items-center justify-center w-full rounded-lg py-1.5 bg-surface border border-border text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors"
          >
            {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
          </button>
        </div>
      </div>

      {/* User profile footer */}
      <div className="fixed-width-col">
        <div className="pt-2.5 border-t border-border px-1">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-surface border border-border flex items-center justify-center font-mono text-[11px] text-foreground font-semibold shrink-0">
              U{USER_ID}
            </div>
            <span className={`text-xs text-muted-foreground font-medium whitespace-nowrap ${collapsed ? "opacity-0" : "opacity-100"} transition-opacity`}>
              Student #{USER_ID}
            </span>
            <span className={`text-[10px] text-muted-foreground font-mono ml-auto ${collapsed ? "opacity-0" : "opacity-100"} transition-opacity`}>v1.0</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
