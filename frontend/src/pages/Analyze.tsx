import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Radar, FlaskConical, Satellite } from "lucide-react";
import AgriGisMap from "@/components/gis/AgriGisMap";
import AnalysisPipelineTracker from "@/components/analysis/AnalysisPipelineTracker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiGet, apiPost } from "@/lib/api";
import { INDIA_STATES } from "@/lib/india";
import type { AnalysisJob, DiscoverOut } from "@/lib/types";

export default function Analyze() {
  const nav = useNavigate();
  const [boundary, setBoundary] = useState<number[][] | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  const [saveField, setSaveField] = useState(true);
  const [fieldName, setFieldName] = useState("");
  const [stateName, setStateName] = useState("");
  const [district, setDistrict] = useState("");

  const { data: satStatus } = useQuery({
    queryKey: ["satellite-status"],
    queryFn: () => apiGet<{ sentinel_hub_configured: boolean; note: string }>("/satellite/status"),
    retry: false,
  });

  const discover = useMutation({
    mutationFn: () => apiPost<DiscoverOut>("/satellite/discover", { coordinates: boundary }),
    onError: () => toast.error("Satellite discovery failed"),
  });

  const start = useMutation({
    mutationFn: () =>
      apiPost<{ job_id: string }>("/analyze", {
        coordinates: boundary,
        demo,
        save_as_field: saveField,
        field_name: fieldName || undefined,
      }),
    onSuccess: (d) => {
      setJobId(d.job_id);
      toast.success("Analysis started");
    },
    onError: (e: unknown) => {
      const detail = (e as { body?: { detail?: string } }).body?.detail;
      toast.error(typeof detail === "string" ? detail : "Could not start the analysis");
    },
  });

  const { data: job } = useQuery<AnalysisJob>({
    queryKey: ["job", jobId],
    queryFn: () => apiGet<AnalysisJob>(`/analysis/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.state;
      return s && ["COMPLETED", "PARTIAL", "FAILED"].includes(s) ? false : 2000;
    },
  });

  useEffect(() => {
    if (job && ["COMPLETED", "PARTIAL"].includes(job.state) && job.analysis_id) {
      toast.success(job.state === "PARTIAL" ? "Partial analysis ready" : "Analysis complete");
      nav(`/app/analyses/${job.analysis_id}`);
    }
  }, [job, nav]);

  return (
    <div className="max-w-[1800px] mx-auto p-4 sm:p-6 grid grid-cols-1 xl:grid-cols-12 gap-6">
      <div className="xl:col-span-8 space-y-4">
        <div>
          <h1 className="text-3xl font-bold">Run an analysis</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Draw your farm boundary, then AgriGaurd runs the full pipeline: satellite discovery → SAR flood
            detection → water & built-up verification → cropland masking → soil, terrain, weather → land
            suitability → crop recommendation.
          </p>
        </div>

        {satStatus && !satStatus.sentinel_hub_configured && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-950/30 px-4 py-3 text-xs text-amber-200"
               data-testid="sentinel-not-configured">
            <b>Sentinel Hub credentials are not configured on this server.</b> Sentinel-1/Sentinel-2 flood
            detection will report <span className="font-mono">DATA UNAVAILABLE</span> — soil, terrain, weather,
            land cover and map context still run. Add SENTINEL_HUB_CLIENT_ID / _SECRET to backend/.env, or tick
            Demo mode below to explore the full pipeline with a prepared sample dataset.
          </div>
        )}

        <AgriGisMap onBoundary={setBoundary} height={560} />
      </div>

      <div className="xl:col-span-4 space-y-4">
        <Card className="bg-card border-[#1E3A2B]">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Analysis setup</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="fname">Field name</Label>
              <Input id="fname" value={fieldName} onChange={(e) => setFieldName(e.target.value)}
                     placeholder="e.g. North paddy plot" data-testid="analyze-field-name" />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label>State</Label>
                <Select value={stateName} onValueChange={(v: string) => { setStateName(v); setDistrict(""); }}>
                  <SelectTrigger data-testid="analyze-state-select" size="sm">
                    <SelectValue>{(v) => (v as string) || "Select"}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {Object.keys(INDIA_STATES).map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>District</Label>
                <Select value={district} onValueChange={(v: string) => setDistrict(v)}>
                  <SelectTrigger data-testid="analyze-district-select" size="sm">
                    <SelectValue>{(v) => (v as string) || "Select"}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {(INDIA_STATES[stateName] ?? []).map((d) => (
                      <SelectItem key={d} value={d}>{d}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <label className="flex items-center gap-2.5 text-sm cursor-pointer">
              <Checkbox checked={saveField} onCheckedChange={(v) => setSaveField(!!v)}
                        data-testid="analyze-save-field-checkbox" />
              Save this boundary to My Fields
            </label>
            <label className="flex items-center gap-2.5 text-sm cursor-pointer">
              <Checkbox checked={demo} onCheckedChange={(v) => setDemo(!!v)} data-testid="analyze-demo-checkbox" />
              <span>
                Demo mode
                <span className="block text-[10px] text-amber-400/80">
                  Prepared sample dataset — clearly labelled, never mixed with real analyses
                </span>
              </span>
            </label>

            <div className="flex flex-col gap-2 pt-1">
              <Button onClick={() => start.mutate()} disabled={!boundary || start.isPending || !!jobId}
                      data-testid="run-analysis-btn" className="w-full">
                {start.isPending || jobId ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Radar className="w-4 h-4 mr-2" />}
                {jobId ? "Analysis running…" : "Run full analysis"}
              </Button>
              <Button variant="secondary" onClick={() => discover.mutate()} disabled={!boundary || discover.isPending}
                      data-testid="discover-btn" className="w-full">
                {discover.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Satellite className="w-4 h-4 mr-2" />}
                Discover satellite observations
              </Button>
              {jobId && (
                <Button variant="ghost" size="sm" onClick={() => setJobId(null)} data-testid="reset-job-btn">
                  Start over
                </Button>
              )}
            </div>
            {!boundary && (
              <p className="text-[11px] text-muted-foreground" data-testid="no-boundary-hint">
                Draw a polygon or rectangle on the map to enable analysis.
              </p>
            )}
          </CardContent>
        </Card>

        {discover.data && (
          <Card className="bg-card border-[#1E3A2B]" data-testid="discovery-panel">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Satellite data discovery</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {discover.data.sentinel_hub_configured ? (
                <>
                  <p className="text-[11px] text-muted-foreground">{discover.data.note}</p>
                  {discover.data.observations.slice(0, 8).map((o, i) => (
                    <div key={i} className="flex justify-between text-xs border-b border-[#1E3A2B] pb-1 last:border-0"
                         data-testid={`observation-${i}`}>
                      <span className="text-emerald-100/85">{o.satellite}</span>
                      <span className="font-mono text-muted-foreground">
                        {o.acquired?.slice(0, 10)}{o.cloud_pct != null ? ` · ${Math.round(o.cloud_pct)}% cloud` : ""}
                      </span>
                    </div>
                  ))}
                  {!discover.data.observations.length && (
                    <p className="text-xs text-amber-300">No suitable observations found for this area/date range.</p>
                  )}
                </>
              ) : (
                <p className="text-xs text-amber-300" data-testid="discovery-unavailable">{discover.data.message}</p>
              )}
            </CardContent>
          </Card>
        )}

        {job && <AnalysisPipelineTracker job={job} />}

        {demo && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-950/25 p-3 flex gap-2 text-[11px] text-amber-200"
               data-testid="demo-mode-note">
            <FlaskConical className="w-4 h-4 shrink-0" />
            Demo mode runs the identical flood methodology on a prepared synthetic SAR pair so you can verify the
            pipeline end-to-end. Results are tagged DEMO DATA.
          </div>
        )}
      </div>
    </div>
  );
}
