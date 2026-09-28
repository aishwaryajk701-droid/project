import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Bell, LayoutDashboard, LogOut, Map, Microscope, Radar, Satellite, Shield, Activity, Sprout,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiGet } from "@/lib/api";
import { endSession, useSession } from "@/lib/session";
import type { NotificationDoc } from "@/lib/types";

const LINKS = [
  { to: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard, tid: "nav-dashboard" },
  { to: "/app/fields", label: "My Fields", icon: Map, tid: "nav-fields" },
  { to: "/app/analyze", label: "Analyze", icon: Radar, tid: "nav-analyze" },
  { to: "/app/crops", label: "Crops", icon: Sprout, tid: "nav-crops" },
  { to: "/app/seed-ai", label: "Seed AI", icon: Microscope, tid: "nav-seed-ai" },
  { to: "/app/health", label: "System", icon: Activity, tid: "nav-health" },
];

export default function Navbar() {
  const loc = useLocation();
  const nav = useNavigate();
  const { user } = useSession();

  const { data: notes } = useQuery<NotificationDoc[]>({
    queryKey: ["notifications", "unread"],
    queryFn: () => apiGet<NotificationDoc[]>("/notifications?view=unread"),
    refetchInterval: 60_000,
    retry: false,
  });
  const unread = notes?.length ?? 0;

  const logout = async () => {
    await endSession();
    nav("/login", { replace: true });
  };

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0B130E]/90 border-b border-[#1E3A2B]"
            data-testid="app-navbar">
      <div className="max-w-[1800px] mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
        <Link to="/app/dashboard" className="flex items-center gap-2.5 shrink-0" data-testid="brand-link">
          <div className="relative w-9 h-9 rounded-xl bg-emerald-500/15 border border-emerald-500/40 grid place-items-center">
            <Shield className="w-5 h-5 text-emerald-400" />
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 pulse-ring" />
          </div>
          <div className="leading-tight">
            <div className="font-bold tracking-tight text-emerald-50">AgriGaurd</div>
            <div className="text-[9px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
              Satellite Intelligence
            </div>
          </div>
        </Link>

        <nav className="hidden lg:flex items-center gap-1">
          {LINKS.map((l) => {
            const active = loc.pathname.startsWith(l.to);
            const Icon = l.icon;
            return (
              <Link key={l.to} to={l.to} data-testid={l.tid}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
                      active
                        ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                        : "text-muted-foreground hover:text-emerald-50 hover:bg-[#182820]"
                    }`}>
                <Icon className="w-4 h-4" /> {l.label}
              </Link>
            );
          })}
          {user?.role === "ADMIN" && (
            <Link to="/app/admin" data-testid="nav-admin"
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    loc.pathname.startsWith("/app/admin")
                      ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                      : "text-muted-foreground hover:text-cyan-100 hover:bg-[#182820]"
                  }`}>
              <Satellite className="w-4 h-4" /> Admin
            </Link>
          )}
        </nav>

        <div className="flex items-center gap-2">
          <Link to="/app/notifications" data-testid="nav-notifications"
                className="relative p-2 rounded-lg text-muted-foreground hover:text-emerald-300 hover:bg-[#182820] transition-colors">
            <Bell className="w-5 h-5" />
            {unread > 0 && (
              <span data-testid="unread-badge"
                    className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold grid place-items-center">
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </Link>
          {user && (
            <div className="hidden sm:flex flex-col items-end mr-1">
              <span className="text-xs text-emerald-50 font-medium" data-testid="nav-user-email">{user.email}</span>
              <Badge variant="outline" className="text-[9px] py-0 h-4 border-emerald-500/40 text-emerald-400"
                     data-testid="nav-user-role">{user.role}</Badge>
            </div>
          )}
          <Button size="sm" variant="ghost" onClick={logout} data-testid="logout-btn"
                  className="text-muted-foreground hover:text-red-400">
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <div className="lg:hidden flex overflow-x-auto gap-1 px-3 pb-2 custom-scrollbar">
        {LINKS.map((l) => {
          const active = loc.pathname.startsWith(l.to);
          const Icon = l.icon;
          return (
            <Link key={l.to} to={l.to} data-testid={`${l.tid}-mobile`}
                  className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs ${
                    active ? "bg-emerald-500/15 text-emerald-300" : "text-muted-foreground bg-[#182820]"
                  }`}>
              <Icon className="w-3 h-3" /> {l.label}
            </Link>
          );
        })}
      </div>
    </header>
  );
}
