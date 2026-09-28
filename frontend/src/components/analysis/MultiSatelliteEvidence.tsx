import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Satellite, ShieldAlert } from "lucide-react";
import type { MultiSatelliteSummary } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  "STRONG EVIDENCE": "bg-emerald-500/20 text-emerald-300",
  "SUPPORTING EVIDENCE": "bg-sky-500/20 text-sky-300",
  "DATA UNAVAILABLE": "bg-zinc-600/25 text-zinc-400",
  "NOT CONFIGURED": "bg-amber-500/20 text-amber-300",
  "NO COVERAGE": "bg-amber-500/20 text-amber-300",
};

export default function MultiSatelliteEvidence({ data }: { data: MultiSatelliteSummary }) {
  return (
    <Card className="bg-card border-[#1E3A2B]" data-testid="multisat-evidence">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Satellite className="w-4 h-4 text-emerald-400" />
          Multi-satellite evidence — {data.available_count}/{data.total_count} sources contributed
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm" data-testid="multisat-agreement">
          <span className="font-mono text-emerald-300">{data.agreement.status}</span>
          {" — "}{data.agreement.note}
        </p>

        <div className="space-y-1.5">
          {data.sources.map((s) => (
            <div key={s.key} className="grid sm:grid-cols-[150px_130px_1fr] gap-x-3 gap-y-0.5 py-1.5 border-b border-[#1E3A2B]/60 last:border-0"
                 data-testid={`multisat-row-${s.key}`}>
              <span className="text-xs font-medium">{s.role}</span>
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded justify-self-start ${STATUS_STYLE[s.status] ?? STATUS_STYLE["DATA UNAVAILABLE"]}`}>
                {s.status}
              </span>
              <span className="text-xs text-muted-foreground">
                {s.detail}
                {s.source ? ` · ${s.source}` : ""}
                {s.acquired ? ` · acquired ${String(s.acquired).slice(0, 10)}` : ""}
                {s.resolution ? ` · ${s.resolution}` : ""}
              </span>
            </div>
          ))}
        </div>

        {data.cross_checks.map((c, i) => (
          <p key={i} className="text-xs text-muted-foreground" data-testid={`multisat-crosscheck-${i}`}>
            <b className="text-sky-300">{c.status}</b> — {c.note}
          </p>
        ))}

        <p className="text-[11px] text-muted-foreground flex gap-2" data-testid="multisat-disclaimer">
          <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          {data.disclaimer} {data.separation_note}
        </p>
      </CardContent>
    </Card>
  );
}
