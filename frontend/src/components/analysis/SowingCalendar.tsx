import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CalendarDays, CloudRain, Droplets, Info } from "lucide-react";
import type { SowingCalendarOut } from "@/lib/types";

const VERDICT_STYLE: Record<string, string> = {
  "SOW NOW": "bg-emerald-500 text-emerald-950 font-bold",
  SOW: "bg-emerald-500/30 text-emerald-200",
  PREPARE: "bg-sky-500/25 text-sky-200",
  WAIT: "bg-amber-500/30 text-amber-200",
  UNCERTAIN: "bg-zinc-500/25 text-zinc-300",
  AVOID: "bg-red-500/20 text-red-300",
};

export default function SowingCalendar({ data }: { data: SowingCalendarOut }) {
  return (
    <div className="space-y-4" data-testid="sowing-calendar">
      <Card className="bg-card border-[#1E3A2B]">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-emerald-400" />
            Sowing calendar — {data.month_label} ({data.season})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-4 text-xs font-mono">
            <span className="flex items-center gap-1.5" data-testid="sowing-rainfall">
              <CloudRain className="w-3.5 h-3.5 text-sky-400" />
              7-day rain: {data.rainfall.last_7_days_mm ?? "DATA UNAVAILABLE"}
              {data.rainfall.last_7_days_mm != null ? " mm" : ""}
            </span>
            <span className="flex items-center gap-1.5" data-testid="sowing-rain30">
              30-day: {data.rainfall.last_30_days_mm ?? "—"}
              {data.rainfall.last_30_days_mm != null ? " mm" : ""}
            </span>
            <span className="flex items-center gap-1.5" data-testid="sowing-flood">
              <Droplets className="w-3.5 h-3.5 text-cyan-400" />
              Flood: {data.flood_severity ?? "DATA UNAVAILABLE"}
              {data.agricultural_flood_pct != null ? ` · ${data.agricultural_flood_pct}%` : ""}
            </span>
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {Object.keys(VERDICT_STYLE).map((k) => (
              <span key={k} className={`px-2 py-0.5 rounded text-[10px] font-mono ${VERDICT_STYLE[k]}`}>{k}</span>
            ))}
          </div>
        </CardContent>
      </Card>

      {!data.crops.length && (
        <p className="text-sm text-muted-foreground" data-testid="sowing-empty">
          No crop recommendations on the latest analysis yet.
        </p>
      )}

      {data.crops.map((c) => (
        <Card key={c.crop} className="bg-card border-[#1E3A2B]" data-testid={`sowing-crop-${c.crop}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-baseline justify-between gap-3 flex-wrap">
              <span>{c.crop}</span>
              <span className="font-mono text-xs text-muted-foreground">
                score {c.score ?? "—"}/100 · {c.duration_days} d · flood tol. {c.flood_tolerance}/5
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-6 sm:grid-cols-12 gap-1" data-testid={`sowing-months-${c.crop}`}>
              {c.months.map((m) => (
                <div key={m.month} title={m.reason}
                     className={`rounded-md px-1 py-1.5 text-center transition-colors duration-200 ${VERDICT_STYLE[m.verdict] ?? VERDICT_STYLE.UNCERTAIN}`}>
                  <div className="text-[10px] font-mono">{m.label}</div>
                </div>
              ))}
            </div>
            <div className="text-xs space-y-1">
              <p data-testid={`sowing-verdict-${c.crop}`}>
                <b className="text-emerald-300">{c.current_verdict}</b> this month — {c.current_reason}
              </p>
              {!!c.sow_window.length && (
                <p className="text-muted-foreground">Usual sowing window: {c.sow_window.join(", ")}</p>
              )}
              {c.drainage_wait_days > 0 && (
                <p className="text-amber-300">Allow ~{c.drainage_wait_days} days of drainage before sowing.</p>
              )}
              <p className="text-muted-foreground">{c.factors.moisture.note}</p>
              <p className="text-muted-foreground">{c.factors.flood.note}</p>
              <p className="text-amber-300/80">{c.factors.limits}</p>
            </div>
          </CardContent>
        </Card>
      ))}

      <p className="text-[11px] text-muted-foreground flex gap-2" data-testid="sowing-methodology">
        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        {data.methodology}
      </p>
    </div>
  );
}
