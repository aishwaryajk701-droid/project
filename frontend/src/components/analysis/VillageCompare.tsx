import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Users, ShieldCheck } from "lucide-react";
import type { VillageCompareOut } from "@/lib/types";

function Metric({ label, agg, testid }: {
  label: string;
  agg: VillageCompareOut["flood"];
  testid: string;
}) {
  return (
    <Card className="bg-card border-[#1E3A2B]" data-testid={testid}>
      <CardHeader className="pb-1"><CardTitle className="text-sm">{label}</CardTitle></CardHeader>
      <CardContent className="space-y-1 text-xs font-mono">
        <div className="text-2xl font-bold text-emerald-300" data-testid={`${testid}-yours`}>
          {agg.your_value ?? "—"}
        </div>
        <div className="text-muted-foreground">Local average: {agg.average ?? "—"}</div>
        <div className="text-muted-foreground">Median: {agg.median ?? "—"} · range {agg.min ?? "—"}–{agg.max ?? "—"}</div>
        <div className="text-muted-foreground">
          Percentile: {agg.your_percentile != null ? `${agg.your_percentile}%` : "—"} of {agg.count} fields
        </div>
      </CardContent>
    </Card>
  );
}

export default function VillageCompare({ data }: { data: VillageCompareOut }) {
  return (
    <div className="space-y-4" data-testid="village-compare">
      <Card className="bg-card border-[#1E3A2B]">
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="w-4 h-4 text-emerald-400" />
            Village compare — {data.analysed_neighbour_count} analysed of {data.neighbour_count} fields within {data.radius_km} km
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.status !== "OK" && (
            <p className="text-sm text-amber-300" data-testid="village-insufficient">
              {data.status} — {data.verdicts[0]}
            </p>
          )}
          {data.verdicts.map((v, i) => (
            <p key={i} className="text-sm" data-testid={`village-verdict-${i}`}>{v}</p>
          ))}
          <p className="text-[11px] text-muted-foreground flex gap-2 pt-1">
            <ShieldCheck className="w-3.5 h-3.5 shrink-0 mt-0.5" />{data.privacy}
          </p>
        </CardContent>
      </Card>

      <div className="grid sm:grid-cols-2 gap-3">
        <Metric label="Agricultural flood %" agg={data.flood} testid="village-flood" />
        <Metric label="Land suitability /100" agg={data.suitability} testid="village-suitability" />
      </div>

      {!!data.popular_crops.length && (
        <Card className="bg-card border-[#1E3A2B]" data-testid="village-popular-crops">
          <CardHeader className="pb-1"><CardTitle className="text-sm">Most recommended crops nearby</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {data.popular_crops.map((c) => (
              <span key={c.crop} className="px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-200 text-xs">
                {c.crop} · {c.fields}
              </span>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="bg-card border-[#1E3A2B] p-0 overflow-hidden" data-testid="village-peers-table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead><TableHead>Distance</TableHead><TableHead>Area</TableHead>
              <TableHead>Flood %</TableHead><TableHead>Suitability</TableHead><TableHead>Crop</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!data.peers.length && (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                No other fields mapped within {data.radius_km} km yet.
              </TableCell></TableRow>
            )}
            {data.peers.map((p, i) => (
              <TableRow key={i} data-testid={`village-peer-${i}`}>
                <TableCell className="text-xs">
                  {p.name}{p.own_field ? " (yours)" : ""}
                </TableCell>
                <TableCell className="font-mono text-xs">{p.distance_km} km</TableCell>
                <TableCell className="font-mono text-xs">{p.area_ha ?? "—"} ha</TableCell>
                <TableCell className="font-mono text-xs">{p.flood_pct ?? "—"}</TableCell>
                <TableCell className="font-mono text-xs">{p.land_suitability ?? "—"}</TableCell>
                <TableCell className="text-xs">{p.recommended_crop ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
