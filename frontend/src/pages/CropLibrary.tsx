import { useQuery } from "@tanstack/react-query";
import { Loader2, Sprout } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiGet } from "@/lib/api";
import type { CropKBEntry } from "@/lib/types";

export default function CropLibrary() {
  const { data, isLoading } = useQuery<{ crops: CropKBEntry[]; count: number; note: string }>({
    queryKey: ["crops"], queryFn: () => apiGet("/crops"), retry: false,
  });

  return (
    <div className="max-w-[1500px] mx-auto p-4 sm:p-6 space-y-5" data-testid="crop-library-page">
      <div>
        <h1 className="text-3xl font-bold">Crop knowledge base</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Agronomic requirement ranges used by the recommendation engine. {data?.note}
        </p>
      </div>

      {isLoading && <Loader2 className="w-5 h-5 animate-spin text-emerald-400" />}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data?.crops?.map((c) => (
          <Card key={c.name} className="bg-card border-[#1E3A2B] hover:border-emerald-500/50 transition-colors"
                data-testid={`crop-kb-${c.name.replace(/[^a-zA-Z]+/g, "-").toLowerCase()}`}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Sprout className="w-4 h-4 text-emerald-400" /> {c.name}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-1.5">
                <div><span className="text-muted-foreground">pH</span> <span className="font-mono">{c.ph_min}–{c.ph_max}</span></div>
                <div><span className="text-muted-foreground">Temp</span> <span className="font-mono">{c.temp_min}–{c.temp_max}°C</span></div>
                <div><span className="text-muted-foreground">Moisture</span> <span className="font-mono">{c.moisture_need}</span></div>
                <div><span className="text-muted-foreground">Flood tol.</span> <span className="font-mono">{c.flood_tolerance}/5</span></div>
                <div><span className="text-muted-foreground">Duration</span> <span className="font-mono">{c.duration_days} d</span></div>
              </div>
              <div className="flex flex-wrap gap-1">
                {c.seasons.map((s) => <Badge key={s} variant="outline" className="text-[9px] border-cyan-500/40 text-cyan-300">{s}</Badge>)}
              </div>
              <div className="text-muted-foreground">Texture: {c.texture.join(", ")}</div>
              <div className="text-muted-foreground">Regions: {c.regions.slice(0, 4).join(", ")}</div>
              <div className="text-amber-300/85 pt-1 border-t border-[#1E3A2B]">{c.limits}</div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
