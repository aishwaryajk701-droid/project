import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Check, TriangleAlert, Info } from "lucide-react";
import type { Confidence, DataQuality, EvidenceItem } from "@/lib/types";

export function SeverityBadge({ severity, testid = "severity-badge" }: { severity: string; testid?: string }) {
  const map: Record<string, string> = {
    none: "bg-emerald-950 text-emerald-300 border-emerald-700",
    low: "bg-yellow-950 text-yellow-300 border-yellow-700",
    moderate: "bg-amber-950 text-amber-300 border-amber-700",
    high: "bg-red-950 text-red-300 border-red-700",
    critical: "bg-red-600 text-white border-red-400",
  };
  const label = severity === "none" ? "No significant flood" : severity;
  return (
    <span data-testid={testid}
          className={`px-2.5 py-1 rounded-md border text-[11px] font-mono uppercase tracking-wider ${map[severity] ?? map.none}`}>
      {label}
    </span>
  );
}

export function Stat({ label, value, unit, testid, hint }: {
  label: string; value: React.ReactNode; unit?: string; testid?: string; hint?: string;
}) {
  const unavailable = value === null || value === undefined || value === "";
  return (
    <div className="bg-[#0B130E] border border-[#1E3A2B] rounded-xl p-3" data-testid={testid}>
      <div className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="text-xl font-bold mt-1 text-emerald-50">
        {unavailable ? <span className="text-xs text-amber-400">DATA UNAVAILABLE</span> : value}
        {!unavailable && unit && <span className="text-xs text-muted-foreground ml-1">{unit}</span>}
      </div>
      {hint && <div className="text-[10px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

export function EvidenceList({ evidence, testid = "evidence-list" }: {
  evidence: { positive: EvidenceItem[]; warnings: EvidenceItem[] }; testid?: string;
}) {
  return (
    <div className="space-y-1.5" data-testid={testid}>
      {evidence.positive?.map((e, i) => (
        <div key={`p${i}`} className="flex gap-2 text-sm text-emerald-100/90" data-testid={`evidence-ok-${i}`}>
          <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <span>{e.text}</span>
        </div>
      ))}
      {evidence.warnings?.map((e, i) => (
        <div key={`w${i}`} className="flex gap-2 text-sm text-amber-100/85" data-testid={`evidence-warn-${i}`}>
          <TriangleAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <span>{e.text}</span>
        </div>
      ))}
    </div>
  );
}

export function ConfidenceBreakdown({ confidence }: { confidence: Confidence }) {
  return (
    <Card className="bg-card border-[#1E3A2B]" data-testid="confidence-breakdown">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center justify-between">
          <span>Analytical Confidence</span>
          <span className="font-mono text-2xl text-emerald-400" data-testid="confidence-score">
            {confidence.score}<span className="text-xs text-muted-foreground">/100</span>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Badge variant="outline" data-testid="confidence-label"
               className="border-emerald-500/40 text-emerald-300">{confidence.label}</Badge>
        {Object.entries(confidence.factors).map(([key, f]) => (
          <div key={key} data-testid={`confidence-factor-${key}`}>
            <div className="flex justify-between text-xs mb-0.5">
              <span className="text-emerald-100/80">
                {key.replace(/_/g, " ")}
                <span className="text-muted-foreground ml-1 font-mono">
                  {confidence.weights[key] ?? 0}%
                </span>
              </span>
              <span className="font-mono text-emerald-300">{f.value}</span>
            </div>
            <div className="h-1.5 rounded-full bg-[#0B130E] overflow-hidden">
              <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-[width] duration-500"
                   style={{ width: `${Math.max(0, Math.min(100, f.value))}%` }} />
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">{f.note}</div>
          </div>
        ))}
        <p className="text-[10px] text-muted-foreground flex gap-1.5 pt-1 border-t border-[#1E3A2B]">
          <Info className="w-3 h-3 shrink-0 mt-0.5" /> {confidence.disclaimer}
        </p>
      </CardContent>
    </Card>
  );
}

export function DataQualityCard({ quality }: { quality: DataQuality }) {
  const color = quality.label === "High" ? "text-emerald-400"
    : quality.label === "Moderate" ? "text-amber-400" : "text-red-400";
  return (
    <Card className="bg-card border-[#1E3A2B]" data-testid="data-quality-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center justify-between">
          <span>Data Quality</span>
          <span className={`font-mono text-2xl ${color}`} data-testid="data-quality-score">
            {quality.score}<span className="text-xs text-muted-foreground">/100</span>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        <Badge variant="outline" data-testid="data-quality-label"
               className="border-emerald-500/40 text-emerald-300">{quality.label}</Badge>
        {Object.entries(quality.components).map(([k, c]) => (
          <div key={k} className="flex justify-between text-xs" data-testid={`dq-${k}`}>
            <span className="text-emerald-100/75">{k.replace(/_/g, " ")}</span>
            <span className="font-mono text-muted-foreground">{c.score}/{c.max}</span>
          </div>
        ))}
        {quality.missing_sources.length > 0 && (
          <div className="text-[11px] text-amber-300 pt-1 border-t border-[#1E3A2B]" data-testid="dq-missing">
            Missing: {quality.missing_sources.join(", ")}
          </div>
        )}
        <p className="text-[10px] text-muted-foreground">{quality.note}</p>
      </CardContent>
    </Card>
  );
}

export function DemoBanner() {
  return (
    <div data-testid="demo-banner"
         className="rounded-xl border-2 border-amber-500/60 bg-amber-950/40 px-4 py-3 flex items-center gap-3">
      <TriangleAlert className="w-5 h-5 text-amber-400 shrink-0" />
      <div>
        <div className="font-bold text-amber-200 text-sm tracking-wide">DEMO DATA — NOT LIVE SATELLITE DATA</div>
        <div className="text-[11px] text-amber-100/70">
          Prepared sample dataset so you can explore the full pipeline. Demo results never mix with real analyses.
        </div>
      </div>
    </div>
  );
}

export function Limitations({ items }: { items: string[] }) {
  return (
    <p className="text-[10px] text-muted-foreground" data-testid="limitations-note">
      {items.join(" · ")}
    </p>
  );
}
