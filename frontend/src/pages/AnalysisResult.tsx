import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText, Loader2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import AgriGisMap from "@/components/gis/AgriGisMap";
import {
  ConfidenceBreakdown, DataQualityCard, DemoBanner, EvidenceList, Limitations, SeverityBadge, Stat,
} from "@/components/analysis/Primitives";
import { apiGet } from "@/lib/api";
import type { AnalysisDoc } from "@/lib/types";

const TABS = ["flood", "water", "land", "soil", "terrain", "weather", "vegetation", "crops", "evidence"];

export default function AnalysisResult() {
  const { analysisId } = useParams();
  const { data: a, isLoading, isError } = useQuery<AnalysisDoc>({
    queryKey: ["analysis", analysisId],
    queryFn: () => apiGet<AnalysisDoc>(`/analyses/${analysisId}`),
    retry: false,
  });

  if (isLoading) {
    return <div className="grid place-items-center py-24"><Loader2 className="w-6 h-6 animate-spin text-emerald-400" /></div>;
  }
  if (isError || !a) {
    return <div className="max-w-3xl mx-auto p-6 text-sm text-amber-300" data-testid="analysis-unavailable">
      This analysis could not be loaded.
    </div>;
  }

  const f = a.flood;
  const wc = a.water_classification;
  const lc = a.landcover;

  return (
    <div className="max-w-[1800px] mx-auto p-4 sm:p-6 space-y-5" data-testid="analysis-result-page">
      {a.demo && <DemoBanner />}

      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
            {a.status === "PARTIAL" ? "Partial analysis" : "Analysis"} · {a.analysis_date}
          </div>
          <h1 className="text-3xl font-bold">{a.boundary?.name ?? "Field analysis"}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {a.area_ha} ha · {[a.village, a.district, a.state].filter(Boolean).join(", ") || "location not set"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" data-testid="report-pdf-btn"
                  onClick={() => window.open(`/api/reports/analyses/${a.id}/report.pdf`, "_blank")}>
            <FileText className="w-4 h-4 mr-2" /> PDF report
          </Button>
          <Button variant="secondary" data-testid="export-csv-btn"
                  onClick={() => window.open(`/api/analyses/${a.id}/export/csv`, "_blank")}>
            <Download className="w-4 h-4 mr-2" /> CSV
          </Button>
          <Button variant="secondary" data-testid="export-json-btn"
                  onClick={() => window.open(`/api/analyses/${a.id}/export/json`, "_blank")}>
            JSON
          </Button>
        </div>
      </div>

      {a.status === "PARTIAL" && a.message && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-950/25 px-4 py-2.5 text-xs text-amber-200"
             data-testid="partial-analysis-note">{a.message}</div>
      )}

      {/* headline */}
      <section className="grid grid-cols-2 lg:grid-cols-6 gap-3" data-testid="flood-headline">
        <Stat label="Flood status" value={f.status} testid="res-flood-status" />
        <Stat label="Total water" value={f.total_water_pct} unit="%" testid="res-total-water" />
        <Stat label="New water" value={f.new_water_pct} unit="%" testid="res-new-water" />
        <Stat label="Agricultural flood" value={f.agricultural_flood_pct} unit="%" testid="res-ag-flood" />
        <Stat label="Affected area" value={f.agricultural_flood_ha} unit="ha" testid="res-affected-ha" />
        <div className="bg-[#0B130E] border border-[#1E3A2B] rounded-xl p-3 flex flex-col justify-center gap-1.5">
          <div className="text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground">Severity</div>
          <SeverityBadge severity={f.severity} testid="res-severity" />
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        <div className="xl:col-span-8 space-y-4">
          <Card className="bg-card border-[#1E3A2B] overflow-hidden p-0" data-testid="result-map-card">
            <AgriGisMap readOnly height={380} initialCoordinates={a.boundary?.coordinates ?? null}
                        overlayPngB64={a.images?.s1_after_png_b64 ?? null} overlayOpacity={0.55} />
          </Card>

          {(a.images?.s1_before_png_b64 && a.images?.s1_after_png_b64) && (
            <Card className="bg-card border-[#1E3A2B]" data-testid="before-after-card">
              <CardHeader className="pb-2"><CardTitle className="text-base">Before / after observation</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-3">
                <div>
                  <img src={`data:image/png;base64,${a.images.s1_before_png_b64}`} alt="before"
                       className="rounded-lg border border-[#1E3A2B] w-full" data-testid="before-image" />
                  <div className="text-[10px] font-mono text-center text-muted-foreground mt-1">
                    BEFORE · {a.before_window?.from ?? "—"}
                  </div>
                </div>
                <div>
                  <img src={`data:image/png;base64,${a.images.s1_after_png_b64}`} alt="after"
                       className="rounded-lg border border-cyan-500/40 w-full" data-testid="after-image" />
                  <div className="text-[10px] font-mono text-center text-muted-foreground mt-1">
                    AFTER · {a.after_window?.to ?? "—"}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <Tabs defaultValue="flood">
            <TabsList variant="line" className="flex-wrap h-auto" data-testid="result-tabs">
              {TABS.map((t) => (
                <TabsTrigger key={t} value={t} data-testid={`tab-${t}`} className="capitalize">{t}</TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="flood" className="pt-3 space-y-3" data-testid="panel-flood">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Water expansion" value={f.sar?.water_expansion_pct} unit="%" />
                <Stat label="VV change" value={f.sar?.vv_change_db} unit="dB" />
                <Stat label="VH change" value={f.sar?.vh_change_db} unit="dB" />
                <Stat label="Valid SAR pixels" value={f.sar?.valid_pixels} />
              </div>
              {!f.available && (
                <p className="text-xs text-amber-300" data-testid="sar-unavailable">
                  {f.sar?.reason ?? "Sentinel-1 data unavailable — flood metrics are DATA UNAVAILABLE, not estimated."}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground">
                Severity thresholds (agricultural flood %): {JSON.stringify(f.severity_thresholds)}
              </p>
            </TabsContent>

            <TabsContent value="water" className="pt-3 space-y-3" data-testid="panel-water">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Permanent" value={wc?.permanent_pct} unit="%" testid="water-permanent" />
                <Stat label="Seasonal" value={wc?.seasonal_pct} unit="%" testid="water-seasonal" />
                <Stat label="New flood" value={wc?.new_flood_pct} unit="%" testid="water-new" />
                <Stat label="Uncertain" value={wc?.uncertain_pct} unit="%" testid="water-uncertain" />
              </div>
              <p className="text-sm text-emerald-100/85">Classification: <b data-testid="water-classification">{wc?.classification}</b></p>
              <p className="text-xs text-muted-foreground">{wc?.note}</p>
              <div className="text-xs space-y-1.5 pt-2 border-t border-[#1E3A2B]">
                <p data-testid="rivers-note"><b className="text-cyan-300">Rivers / lakes:</b> {a.water_verification?.rivers_lakes?.note}</p>
                <p data-testid="builtup-note"><b className="text-amber-300">Built-up:</b> {a.water_verification?.builtup?.note}</p>
              </div>
            </TabsContent>

            <TabsContent value="land" className="pt-3 space-y-3" data-testid="panel-land">
              {lc?.composition ? (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {Object.entries(lc.composition).map(([k, v]) => (
                      <Stat key={k} label={k} value={v} unit="%" testid={`landcover-${k.replace(/\s+/g, "-").toLowerCase()}`} />
                    ))}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {lc.source} · {lc.resolution}
                  </p>
                </>
              ) : (
                <p className="text-xs text-amber-300" data-testid="landcover-unavailable">
                  Land cover DATA UNAVAILABLE — {lc?.worldcover?.error ?? "source unreachable"}. OSM landuse context was used where possible.
                </p>
              )}
            </TabsContent>

            <TabsContent value="soil" className="pt-3 space-y-3" data-testid="panel-soil">
              {a.soil ? (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {Object.entries(a.soil.properties).map(([k, p]) => (
                      <Stat key={k} label={p.label} value={p.value} unit={p.unit} testid={`soil-${k}`} />
                    ))}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Texture: {a.soil.texture_class?.class ?? "—"} · {a.soil.source} · resolution {a.soil.resolution} · depth {a.soil.depth}
                  </p>
                </>
              ) : (
                <p className="text-xs text-amber-300" data-testid="soil-unavailable">
                  Soil DATA UNAVAILABLE ({a.soil_status}) — the rest of the analysis continued.
                </p>
              )}
            </TabsContent>

            <TabsContent value="terrain" className="pt-3 space-y-3" data-testid="panel-terrain">
              {a.terrain ? (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <Stat label="Elevation mean" value={a.terrain.elevation_mean_m} unit="m" testid="terrain-elev" />
                    <Stat label="Elevation range" value={a.terrain.elevation_range_m} unit="m" />
                    <Stat label="Median slope" value={a.terrain.slope_median_pct} unit="%" testid="terrain-slope" />
                    <Stat label="Low-lying" value={a.terrain.low_lying_pct} unit="%" testid="terrain-lowlying" />
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Terrain risk: {a.terrain.terrain_risk} · {a.terrain.source} ({a.terrain.resolution}) · supporting evidence only
                  </p>
                </>
              ) : <p className="text-xs text-amber-300">Terrain DATA UNAVAILABLE ({a.terrain_status}).</p>}
            </TabsContent>

            <TabsContent value="weather" className="pt-3 space-y-3" data-testid="panel-weather">
              {a.weather ? (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <Stat label="7-day rainfall" value={a.weather.recent?.last_7_days_mm} unit="mm" testid="weather-rain7" />
                    <Stat label="30-day rainfall" value={a.weather.recent?.total_mm} unit="mm" />
                    <Stat label="Max daily rain" value={a.weather.recent?.max_daily_mm} unit="mm" />
                    <Stat label="Temperature"
                          value={(a.weather.current as { temperature_2m?: number })?.temperature_2m} unit="°C"
                          testid="weather-temp" />
                  </div>
                  <p className="text-xs text-emerald-100/85" data-testid="rainfall-statement">{a.weather.verdict?.statement}</p>
                  <p className="text-[11px] text-muted-foreground">{a.weather.source} · {a.weather.resolution}</p>
                </>
              ) : <p className="text-xs text-amber-300">Weather DATA UNAVAILABLE ({a.weather_status}).</p>}
            </TabsContent>

            <TabsContent value="vegetation" className="pt-3 space-y-3" data-testid="panel-vegetation">
              <div className="grid grid-cols-2 gap-2">
                <Stat label="NDVI mean" value={a.ndvi?.mean?.toFixed?.(3)} testid="veg-ndvi" />
                <Stat label="NDMI mean" value={a.ndmi?.mean?.toFixed?.(3)} testid="veg-ndmi" />
              </div>
              <p className="text-xs text-amber-200" data-testid="optical-note">{a.optical_note}</p>
            </TabsContent>

            <TabsContent value="crops" className="pt-3 space-y-3" data-testid="panel-crops">
              <p className="text-[11px] text-muted-foreground">
                Season: {a.crops?.season} · {a.crops?.methodology}
              </p>
              {a.crops?.recommendations?.map((c, i) => (
                <Card key={c.crop} className="bg-[#0B130E] border-[#1E3A2B]" data-testid={`crop-card-${i}`}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center justify-between">
                      <span>{c.crop}</span>
                      <span className="font-mono text-emerald-400" data-testid={`crop-score-${i}`}>
                        {c.score}<span className="text-xs text-muted-foreground">/100</span>
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                      {c.factors.filter((x) => x.value != null).map((x) => (
                        <div key={x.factor} className="flex justify-between border-b border-[#1E3A2B] pb-0.5">
                          <span className="text-muted-foreground">{x.factor}</span>
                          <span className="font-mono text-emerald-300">{x.value}</span>
                        </div>
                      ))}
                    </div>
                    <div><b className="text-emerald-300">Why suitable:</b> {c.why.join("; ")}</div>
                    <div><b className="text-amber-300">Risks / not ideal:</b> {c.risks.slice(0, 3).join("; ")}</div>
                    <div className="text-muted-foreground">Duration: {c.duration_days} days</div>
                  </CardContent>
                </Card>
              ))}
            </TabsContent>

            <TabsContent value="evidence" className="pt-3 space-y-4" data-testid="panel-evidence">
              <div>
                <h3 className="font-semibold mb-2">Why AgriGaurd reported this result</h3>
                <EvidenceList evidence={f.evidence} />
              </div>
              <div>
                <h3 className="font-semibold mb-2 text-sm">Data sources & transparency</h3>
                <div className="space-y-1 text-xs" data-testid="sources-list">
                  {Object.entries(a.sources ?? {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-[#1E3A2B] pb-0.5">
                      <span className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</span>
                      <span className={v.includes("UNAVAILABLE") || v.includes("NOT CONFIGURED")
                        ? "text-amber-400 font-mono" : "text-emerald-300 font-mono"}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <div className="xl:col-span-4 space-y-4">
          <ConfidenceBreakdown confidence={f.confidence} />

          <Card className="bg-card border-[#1E3A2B]" data-testid="suitability-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center justify-between">
                <span>Land Suitability</span>
                <span className="font-mono text-2xl text-emerald-400" data-testid="suitability-score">
                  {a.land_suitability?.score}<span className="text-xs text-muted-foreground">/100</span>
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(a.land_suitability?.factors ?? {}).map(([k, v]) => (
                <div key={k} data-testid={`suitability-factor-${k}`}>
                  <div className="flex justify-between text-xs mb-0.5">
                    <span className="capitalize text-emerald-100/80">{k}</span>
                    <span className="font-mono text-emerald-300">
                      {v.score ?? <span className="text-amber-400">n/a</span>}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-[#0B130E] overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-cyan-600 to-emerald-400 transition-[width] duration-500"
                         style={{ width: `${v.score ?? 0}%` }} />
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{v.basis}</div>
                </div>
              ))}
              <p className="text-[10px] text-muted-foreground pt-1 border-t border-[#1E3A2B]">
                {a.land_suitability?.disclaimer}
              </p>
            </CardContent>
          </Card>

          <DataQualityCard quality={a.data_quality} />
          <Limitations items={a.limitations ?? []} />
          {a.field_id && (
            <Link to={`/app/fields/${a.field_id}`}>
              <Button variant="secondary" className="w-full" data-testid="open-field-btn">Open field page</Button>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
