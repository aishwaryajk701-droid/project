import { Check, Loader2, Circle, TriangleAlert } from "lucide-react";
import type { AnalysisJob } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  validating: "Location & field boundary validated",
  fetching_data: "Satellite discovery + context data loaded",
  processing_sar: "Sentinel-1 SAR change detection",
  verifying_water: "Permanent water, rivers & built-up verification",
  analyzing_land: "Land cover composition",
  processing_soil: "Soil, DEM & weather loaded",
  generating_recommendation: "Land suitability & crop recommendation",
  saving_result: "Analysis saved to database",
};

const ORDER = [
  "validating", "fetching_data", "processing_sar", "verifying_water",
  "analyzing_land", "processing_soil", "generating_recommendation", "saving_result",
];

export default function AnalysisPipelineTracker({ job }: { job: AnalysisJob }) {
  return (
    <div className="rounded-2xl border border-[#1E3A2B] bg-card p-5 space-y-3" data-testid="pipeline-tracker">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-emerald-50">Analysis pipeline</h3>
        <span data-testid="job-state"
              className={`px-2 py-0.5 rounded-md text-[10px] font-mono uppercase tracking-wider border ${
                job.state === "COMPLETED" ? "border-emerald-500/40 text-emerald-300 bg-emerald-950/50"
                  : job.state === "PARTIAL" ? "border-amber-500/40 text-amber-300 bg-amber-950/50"
                  : job.state === "FAILED" ? "border-red-500/40 text-red-300 bg-red-950/50"
                  : "border-cyan-500/40 text-cyan-300 bg-cyan-950/50"
              }`}>
          {job.state}
        </span>
      </div>

      <div className="space-y-2">
        {ORDER.map((key) => {
          const stage = job.stages?.[key];
          const status = stage?.status ?? "pending";
          return (
            <div key={key} className="flex items-start gap-2.5" data-testid={`stage-${key}`}>
              {status === "done" ? (
                <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : status === "running" ? (
                <Loader2 className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5 animate-spin" />
              ) : (
                <Circle className="w-4 h-4 text-muted-foreground/40 shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <div className={`text-sm ${status === "done" ? "text-emerald-100" : status === "running" ? "text-cyan-100" : "text-muted-foreground"}`}>
                  {STAGE_LABELS[key]}
                </div>
                {stage?.message && (
                  <div className="text-[11px] text-muted-foreground truncate">{stage.message}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {job.state === "FAILED" && job.error && (
        <div className="flex gap-2 text-sm text-red-300 bg-red-950/40 border border-red-500/30 rounded-lg p-3"
             data-testid="job-error">
          <TriangleAlert className="w-4 h-4 shrink-0 mt-0.5" /> {job.error}
        </div>
      )}
      {job.state === "PARTIAL" && (
        <div className="text-[11px] text-amber-300 bg-amber-950/30 border border-amber-500/30 rounded-lg p-2.5"
             data-testid="job-partial-note">
          PARTIAL ANALYSIS — one or more data sources were unavailable. Missing sources are listed in Data Quality;
          nothing was estimated or fabricated.
        </div>
      )}
    </div>
  );
}
