import { useParams, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Loader2, Radar, Bell } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import AgriGisMap from "@/components/gis/AgriGisMap";
import { SeverityBadge, Stat } from "@/components/analysis/Primitives";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import type { AnalysisDoc, CompareOut, FieldDoc, MonitoringConfig, NotificationDoc } from "@/lib/types";

const FREQ = [
  { v: "daily", l: "Daily" },
  { v: "every_3_days", l: "Every 3 days" },
  { v: "weekly", l: "Weekly" },
];

export default function FieldDetail() {
  const { fieldId } = useParams();
  const qc = useQueryClient();

  const { data: field, isLoading } = useQuery<FieldDoc>({
    queryKey: ["field", fieldId], queryFn: () => apiGet<FieldDoc>(`/fields/${fieldId}`), retry: false,
  });
  const { data: history } = useQuery<AnalysisDoc[]>({
    queryKey: ["field-history", fieldId],
    queryFn: () => apiGet<AnalysisDoc[]>(`/fields/${fieldId}/history`), retry: false,
  });
  const { data: monitoring } = useQuery<MonitoringConfig>({
    queryKey: ["monitoring", fieldId],
    queryFn: () => apiGet<MonitoringConfig>(`/fields/${fieldId}/monitoring`), retry: false,
  });
  const { data: notes } = useQuery<NotificationDoc[]>({
    queryKey: ["notifications", "all"], queryFn: () => apiGet<NotificationDoc[]>("/notifications"), retry: false,
  });

  const [a, b] = [history?.[1]?.id, history?.[0]?.id];
  const { data: compare } = useQuery<CompareOut>({
    queryKey: ["compare", a, b],
    queryFn: () => apiGet<CompareOut>(`/analyses/${a}/compare/${b}`),
    enabled: !!a && !!b, retry: false,
  });

  const analyze = useMutation({
    mutationFn: () => apiPost<{ job_id: string }>(`/fields/${fieldId}/analyze`),
    onSuccess: () => { toast.success("Analysis started"); qc.invalidateQueries({ queryKey: ["field-history", fieldId] }); },
  });
  const scanNow = useMutation({
    mutationFn: () => apiPost<{ job_id: string }>(`/fields/${fieldId}/monitoring/scan`),
    onSuccess: () => toast.success("Monitoring scan queued"),
  });
  const setMon = useMutation({
    mutationFn: (v: { frequency: string; enabled: boolean }) => apiPut(`/fields/${fieldId}/monitoring`, v),
    onSuccess: () => { toast.success("Monitoring updated"); qc.invalidateQueries({ queryKey: ["monitoring", fieldId] }); },
  });

  if (isLoading) return <div className="grid place-items-center py-24"><Loader2 className="w-6 h-6 animate-spin text-emerald-400" /></div>;
  if (!field) return <div className="p-6 text-sm text-amber-300">Field not found.</div>;

  const timeline = (history ?? []).slice().reverse().map((h) => ({
    date: h.created_at?.slice(5, 10),
    flood: h.flood?.agricultural_flood_pct ?? 0,
    confidence: h.flood?.confidence?.score ?? 0,
    suitability: h.land_suitability?.score ?? 0,
  }));
  const fieldNotes = (notes ?? []).filter((n) => n.field_id === fieldId);

  const trendLabel = timeline.length < 3 ? "Insufficient data"
    : timeline[timeline.length - 1].flood > timeline[0].flood + 2 ? "Increasing"
    : timeline[timeline.length - 1].flood < timeline[0].flood - 2 ? "Decreasing" : "Stable";

  return (
    <div className="max-w-[1800px] mx-auto p-4 sm:p-6 space-y-5" data-testid="field-detail-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">{field.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {field.area_ha} ha · {[field.village, field.district, field.state].filter(Boolean).join(", ") || "location not set"}
            {" · "}created {field.created_at?.slice(0, 10)}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => analyze.mutate()} disabled={analyze.isPending} data-testid="field-run-analysis-btn">
            {analyze.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Radar className="w-4 h-4 mr-2" />}
            Analyze
          </Button>
          <Button variant="secondary" onClick={() => scanNow.mutate()} disabled={scanNow.isPending}
                  data-testid="field-scan-now-btn">Run scan now</Button>
          <Button variant="secondary" data-testid="field-report-btn"
                  onClick={() => window.open(`/api/reports/fields/${field.id}/report.pdf`, "_blank")}>
            <FileText className="w-4 h-4 mr-2" /> Report
          </Button>
        </div>
      </div>

      <section className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="bg-[#0B130E] border border-[#1E3A2B] rounded-xl p-3 flex flex-col gap-1.5 justify-center">
          <div className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground">Flood status</div>
          <SeverityBadge severity={(field.flood_pct ?? 0) >= 10 ? "high" : (field.flood_pct ?? 0) > 0.5 ? "moderate" : "none"}
                         testid="fd-severity" />
        </div>
        <Stat label="Flood %" value={field.flood_pct} unit="%" testid="fd-flood-pct" />
        <Stat label="Confidence" value={field.flood_confidence} unit="/100" testid="fd-confidence" />
        <Stat label="Land suitability" value={field.land_suitability} unit="/100" testid="fd-suitability" />
        <Stat label="Recommended crop" value={field.recommended_crop} testid="fd-crop" />
      </section>

      <Tabs defaultValue="overview">
        <TabsList variant="line" className="flex-wrap h-auto" data-testid="field-tabs">
          {["overview", "timeline", "compare", "monitoring", "alerts"].map((t) => (
            <TabsTrigger key={t} value={t} data-testid={`field-tab-${t}`} className="capitalize">{t}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="pt-4">
          <Card className="bg-card border-[#1E3A2B] overflow-hidden p-0">
            <AgriGisMap readOnly height={420} initialCoordinates={field.boundary?.coordinates ?? null} />
          </Card>
        </TabsContent>

        <TabsContent value="timeline" className="pt-4 space-y-4" data-testid="panel-timeline">
          <Card className="bg-card border-[#1E3A2B]">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center justify-between">
                <span>Field intelligence timeline</span>
                <span className="text-xs font-mono text-muted-foreground" data-testid="risk-trend">
                  Risk trend: {trendLabel}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {timeline.length > 1 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={timeline}>
                    <CartesianGrid stroke="#1E3A2B" strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke="#9CA3AF" fontSize={11} />
                    <YAxis stroke="#9CA3AF" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#121F18", border: "1px solid #1E3A2B", borderRadius: 8 }} />
                    <Line type="monotone" dataKey="flood" stroke="#06B6D4" strokeWidth={2} name="Ag. flood %" />
                    <Line type="monotone" dataKey="confidence" stroke="#10B981" strokeWidth={2} name="Confidence" />
                    <Line type="monotone" dataKey="suitability" stroke="#F59E0B" strokeWidth={2} name="Suitability" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-muted-foreground py-6 text-center" data-testid="timeline-insufficient">
                  Insufficient data — run more analyses. Historical values are never invented.
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card border-[#1E3A2B] p-0 overflow-hidden" data-testid="history-table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead><TableHead>Status</TableHead><TableHead>Ag. flood %</TableHead>
                  <TableHead>Confidence</TableHead><TableHead>NDVI</TableHead><TableHead>Suitability</TableHead>
                  <TableHead>Crop</TableHead><TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {!history?.length && (
                  <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                    No analyses yet for this field.
                  </TableCell></TableRow>
                )}
                {history?.map((h) => (
                  <TableRow key={h.id} data-testid={`history-row-${h.id}`}>
                    <TableCell className="font-mono text-xs">{h.created_at?.slice(0, 16).replace("T", " ")}</TableCell>
                    <TableCell className="text-xs">{h.status}{h.demo ? " (DEMO)" : ""}</TableCell>
                    <TableCell className="font-mono text-xs">{h.flood?.agricultural_flood_pct ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{h.flood?.confidence?.score ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{h.ndvi?.mean?.toFixed?.(3) ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{h.land_suitability?.score ?? "—"}</TableCell>
                    <TableCell className="text-xs">{h.crops?.recommendations?.[0]?.crop ?? "—"}</TableCell>
                    <TableCell className="text-right">
                      <Link to={`/app/analyses/${h.id}`}>
                        <Button size="xs" variant="ghost" data-testid={`history-open-${h.id}`}>Open</Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="compare" className="pt-4" data-testid="panel-compare">
          <Card className="bg-card border-[#1E3A2B]">
            <CardHeader className="pb-2"><CardTitle className="text-base">Latest vs previous analysis</CardTitle></CardHeader>
            <CardContent>
              {compare ? (
                <Table>
                  <TableHeader>
                    <TableRow><TableHead>Metric</TableHead><TableHead>Previous</TableHead>
                    <TableHead>Latest</TableHead><TableHead>Δ</TableHead><TableHead>%</TableHead></TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(compare.deltas).map(([k, d]) => (
                      <TableRow key={k} data-testid={`compare-row-${k}`}>
                        <TableCell className="text-xs capitalize">{k.replace(/_/g, " ")}</TableCell>
                        <TableCell className="font-mono text-xs">
                          {String(compare.base.metrics[k] ?? "—")}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {String(compare.other.metrics[k] ?? "—")}
                        </TableCell>
                        <TableCell className={`font-mono text-xs ${d.direction === "increase" ? "text-red-400"
                          : d.direction === "decrease" ? "text-emerald-400" : "text-muted-foreground"}`}>
                          {d.absolute ?? d.direction}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{d.pct != null ? `${d.pct}%` : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground py-6 text-center" data-testid="compare-insufficient">
                  Two analyses are needed to compare. Run another analysis.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="monitoring" className="pt-4" data-testid="panel-monitoring">
          <Card className="bg-card border-[#1E3A2B] max-w-lg">
            <CardHeader className="pb-2"><CardTitle className="text-base">Smart monitoring</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <Select value={monitoring?.frequency ?? "weekly"}
                        onValueChange={(v: string) => setMon.mutate({ frequency: v, enabled: true })}>
                  <SelectTrigger data-testid="monitoring-frequency-select" className="w-48">
                    <SelectValue>{(v) => FREQ.find((f) => f.v === v)?.l ?? "Weekly"}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {FREQ.map((f) => <SelectItem key={f.v} value={f.v}>{f.l}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Button variant={monitoring?.enabled ? "destructive" : "default"} size="sm"
                        data-testid="monitoring-toggle-btn"
                        onClick={() => setMon.mutate({ frequency: monitoring?.frequency ?? "weekly", enabled: !monitoring?.enabled })}>
                  {monitoring?.enabled ? "Disable" : "Enable"}
                </Button>
              </div>
              <div className="text-xs text-muted-foreground space-y-1">
                <p>Status: <b className={monitoring?.enabled ? "text-emerald-400" : "text-muted-foreground"}>
                  {monitoring?.enabled ? "active" : "off"}</b></p>
                {monitoring?.next_run && <p>Next scheduled scan: {monitoring.next_run.slice(0, 16).replace("T", " ")}</p>}
                <p>Each scan finds the latest available observation, re-runs the flood engine, compares against the
                   previous analysis and raises an alert on significant change.</p>
              </div>
              <Button variant="secondary" className="w-full" onClick={() => scanNow.mutate()}
                      disabled={scanNow.isPending} data-testid="monitoring-scan-now-btn">
                Run scan now
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts" className="pt-4 space-y-2" data-testid="panel-alerts">
          {!fieldNotes.length && (
            <p className="text-sm text-muted-foreground" data-testid="field-alerts-empty">No alerts for this field yet.</p>
          )}
          {fieldNotes.map((n) => (
            <Card key={n.id} className="bg-card border-[#1E3A2B]" data-testid={`field-alert-${n.id}`}>
              <CardContent className="py-3 flex gap-3">
                <Bell className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <div className="text-sm font-medium">{n.title}</div>
                  <div className="text-xs text-muted-foreground">{n.body}</div>
                  <div className="text-[10px] font-mono text-muted-foreground mt-0.5">{n.created_at?.slice(0, 16).replace("T", " ")}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
