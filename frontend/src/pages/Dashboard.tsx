import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Droplets, Map as MapIcon, Radar, Sprout, TrendingUp } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Stat, SeverityBadge } from "@/components/analysis/Primitives";
import AgriGisMap from "@/components/gis/AgriGisMap";
import { apiGet } from "@/lib/api";
import type { AnalysisDoc, FieldDoc } from "@/lib/types";

export default function Dashboard() {
  const { data: fields, isError: fieldsError } = useQuery<FieldDoc[]>({
    queryKey: ["fields"], queryFn: () => apiGet<FieldDoc[]>("/fields"), retry: false,
  });
  const { data: analyses } = useQuery<AnalysisDoc[]>({
    queryKey: ["analyses", "dash"],
    queryFn: () => apiGet<AnalysisDoc[]>("/analyses?type=satellite&limit=40"), retry: false,
  });

  const list = fields ?? [];
  const monitored = list.filter((f) => f.monitoring?.enabled).length;
  const alerts = list.filter((f) => f.flood_status === "DETECTED").length;
  const highRisk = list.filter((f) => (f.flood_pct ?? 0) >= 10).length;
  const latest = analyses?.[0];

  const trend = (analyses ?? [])
    .slice()
    .reverse()
    .map((a) => ({
      date: a.created_at?.slice(5, 10) ?? "",
      flood: a.flood?.agricultural_flood_pct ?? 0,
      suitability: a.land_suitability?.score ?? 0,
      ndvi: a.ndvi?.mean != null ? Number((a.ndvi.mean * 100).toFixed(1)) : 0,
    }));

  const cropCounts: Record<string, number> = {};
  (analyses ?? []).forEach((a) => {
    const c = a.crops?.recommendations?.[0]?.crop;
    if (c) cropCounts[c] = (cropCounts[c] ?? 0) + 1;
  });
  const cropData = Object.entries(cropCounts).map(([crop, count]) => ({ crop, count })).slice(0, 6);

  return (
    <div className="max-w-[1800px] mx-auto p-4 sm:p-6 space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">Field intelligence dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Remote-sensing based estimates across your farms · field verification recommended
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/app/analyze"><Button data-testid="dash-run-analysis-btn"><Radar className="w-4 h-4 mr-2" />Run analysis</Button></Link>
          <Link to="/app/fields"><Button variant="secondary" data-testid="dash-fields-btn"><MapIcon className="w-4 h-4 mr-2" />My fields</Button></Link>
        </div>
      </div>

      {/* FIELD OVERVIEW */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="field-overview">
        <Stat label="Total fields" value={list.length} testid="stat-total-fields" />
        <Stat label="Active monitoring" value={monitored} testid="stat-monitoring" />
        <Stat label="Flood alerts" value={alerts} testid="stat-flood-alerts" />
        <Stat label="High-risk fields" value={highRisk} hint="≥10% agricultural flood" testid="stat-high-risk" />
      </section>

      {fieldsError && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-950/25 p-3 text-xs text-amber-200"
             data-testid="dash-offline-note">
          Live field data is unavailable right now — the dashboard shell is shown without figures.
        </div>
      )}

      {/* CURRENT STATUS */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <Card className="lg:col-span-5 bg-card border-[#1E3A2B]" data-testid="current-status-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" /> Current status — latest analysis
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {latest ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Flood</span>
                  <SeverityBadge severity={latest.flood?.severity ?? "none"} testid="dash-severity" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Stat label="Agricultural flood" value={latest.flood?.agricultural_flood_pct} unit="%"
                        testid="dash-ag-flood" />
                  <Stat label="Land suitability" value={latest.land_suitability?.score} unit="/100"
                        testid="dash-suitability" />
                  <Stat label="Recommended crop" value={latest.crops?.recommendations?.[0]?.crop}
                        testid="dash-crop" />
                  <Stat label="Data freshness" value={latest.analysis_date} testid="dash-freshness" />
                </div>
                <Link to={`/app/analyses/${latest.id}`} className="block">
                  <Button variant="secondary" size="sm" className="w-full" data-testid="dash-open-latest-btn">
                    Open full analysis
                  </Button>
                </Link>
              </>
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="dash-no-analysis">
                No analyses yet. Draw a field boundary and run your first analysis.
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-7 bg-card border-[#1E3A2B]" data-testid="analytics-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" /> Flood, NDVI & suitability trend
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trend.length > 1 ? (
              <ResponsiveContainer width="100%" height={210}>
                <LineChart data={trend}>
                  <CartesianGrid stroke="#1E3A2B" strokeDasharray="3 3" />
                  <XAxis dataKey="date" stroke="#9CA3AF" fontSize={11} />
                  <YAxis stroke="#9CA3AF" fontSize={11} />
                  <Tooltip contentStyle={{ background: "#121F18", border: "1px solid #1E3A2B", borderRadius: 8 }}
                           formatter={(value: number, name: string) => [value, name]} />
                  <Line type="monotone" dataKey="flood" stroke="#06B6D4" strokeWidth={2} dot={false} name="Ag. flood %" />
                  <Line type="monotone" dataKey="suitability" stroke="#10B981" strokeWidth={2} dot={false} name="Suitability" />
                  <Line type="monotone" dataKey="ndvi" stroke="#F59E0B" strokeWidth={2} dot={false} name="NDVI ×100" />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground py-8 text-center" data-testid="trend-insufficient">
                Insufficient data — run at least two analyses to see a trend. Nothing is invented.
              </p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <Card className="lg:col-span-5 bg-card border-[#1E3A2B]" data-testid="crop-suitability-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Sprout className="w-4 h-4 text-emerald-400" /> Top recommended crops
            </CardTitle>
          </CardHeader>
          <CardContent>
            {cropData.length ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={cropData}>
                  <CartesianGrid stroke="#1E3A2B" strokeDasharray="3 3" />
                  <XAxis dataKey="crop" stroke="#9CA3AF" fontSize={10} interval={0} angle={-18} textAnchor="end" height={54} />
                  <YAxis stroke="#9CA3AF" fontSize={11} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "#121F18", border: "1px solid #1E3A2B", borderRadius: 8 }} />
                  <Bar dataKey="count" fill="#10B981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground py-8 text-center">No crop recommendations yet.</p>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-7 bg-card border-[#1E3A2B] overflow-hidden" data-testid="dash-map-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Droplets className="w-4 h-4 text-cyan-400" /> All your fields
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <AgriGisMap
              readOnly
              height={260}
              initialCoordinates={list[0]?.boundary?.coordinates ?? null}
              extraPolygons={list.slice(0, 20).map((f) => ({
                coordinates: f.boundary?.coordinates ?? [],
                color: (f.flood_pct ?? 0) >= 10 ? "#EF4444" : "#10B981",
                label: `${f.name} · ${f.area_ha} ha`,
              }))}
            />
          </CardContent>
        </Card>
      </section>

      {alerts > 0 && (
        <div className="rounded-xl border border-red-500/40 bg-red-950/30 px-4 py-3 flex items-center gap-3"
             data-testid="dash-alert-banner">
          <AlertTriangle className="w-5 h-5 text-red-400" />
          <span className="text-sm text-red-100">
            {alerts} field{alerts > 1 ? "s" : ""} currently show detected flooding — open the field for the
            supporting evidence.
          </span>
        </div>
      )}
    </div>
  );
}
