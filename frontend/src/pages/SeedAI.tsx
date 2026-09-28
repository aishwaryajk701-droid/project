import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Microscope, Upload, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiPost } from "@/lib/api";

interface SeedResult {
  id: string;
  result: { prediction: string; confidence: number; reasoning?: string; defects?: string[] };
  processed_image_b64?: string;
}
interface BatchResult {
  summary: { total: number; genuine: number; suspicious: number; genuineness_score: number; verdict: string };
  items: { index: number; thumb_b64?: string; result: { prediction: string; confidence: number } }[];
}

export default function SeedAI() {
  const [preview, setPreview] = useState<string | null>(null);
  const [seedType, setSeedType] = useState("");
  const [batch, setBatch] = useState<string[]>([]);

  const single = useMutation({
    mutationFn: () => apiPost<SeedResult>("/seed/analyze", {
      image_base64: preview!.split(",")[1], seed_type: seedType || null,
    }),
    onSuccess: (d) => {
      const p = d.result.prediction;
      if (p === "genuine") toast.success(`Genuine seed (${Math.round(d.result.confidence * 100)}%)`);
      else if (p === "suspicious") toast.error(`Suspicious seed (${Math.round(d.result.confidence * 100)}%)`);
      else toast.warning("Inconclusive — vision model unavailable");
    },
    onError: () => toast.error("Seed analysis failed"),
  });

  const batchRun = useMutation({
    mutationFn: () => apiPost<BatchResult>("/seed/batch-analyze", {
      images_base64: batch, seed_type: seedType || null,
    }),
    onSuccess: (d) => toast.success(`Batch ${d.summary.verdict} · score ${d.summary.genuineness_score}`),
    onError: () => toast.error("Batch analysis failed"),
  });

  const read = (file: File, cb: (s: string) => void) => {
    const r = new FileReader();
    r.onload = () => cb(String(r.result));
    r.readAsDataURL(file);
  };

  return (
    <div className="max-w-[1500px] mx-auto p-4 sm:p-6 space-y-5" data-testid="seed-ai-page">
      <div>
        <h1 className="text-3xl font-bold">Seed AI inspection</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Vision screening for seed genuineness. Independent of satellite analysis — advisory only.
        </p>
      </div>

      <Tabs defaultValue="single">
        <TabsList variant="line" data-testid="seed-mode-tabs">
          <TabsTrigger value="single" data-testid="seed-tab-single">Single seed</TabsTrigger>
          <TabsTrigger value="batch" data-testid="seed-tab-batch">Batch tray</TabsTrigger>
        </TabsList>

        <TabsContent value="single" className="pt-4 grid lg:grid-cols-2 gap-4">
          <Card className="bg-card border-[#1E3A2B]">
            <CardHeader className="pb-2"><CardTitle className="text-base">Capture or upload</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2 flex-wrap">
                <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-[#1E3A2B] text-sm cursor-pointer hover:border-emerald-500/50 transition-colors">
                  <Upload className="w-4 h-4" /> Upload image
                  <input type="file" accept="image/jpeg,image/png,image/webp" hidden
                         data-testid="seed-upload-input"
                         onChange={(e) => { const f = e.target.files?.[0]; if (f) read(f, setPreview); }} />
                </label>
                <Input value={seedType} onChange={(e) => setSeedType(e.target.value)}
                       placeholder="Seed type (optional)" data-testid="seed-type-input" className="flex-1 min-w-[160px]" />
              </div>
              <div className="rounded-xl border border-[#1E3A2B] bg-[#0B130E] aspect-video grid place-items-center overflow-hidden">
                {preview ? <img src={preview} alt="seed" className="w-full h-full object-contain" data-testid="seed-preview" />
                  : <div className="text-center text-muted-foreground">
                      <Microscope className="w-10 h-10 mx-auto mb-2 opacity-50" />
                      <div className="text-sm">Upload a seed photo</div>
                    </div>}
              </div>
              <Button onClick={() => single.mutate()} disabled={!preview || single.isPending}
                      data-testid="seed-analyze-btn" className="w-full">
                {single.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Zap className="w-4 h-4 mr-2" />}
                Analyze seed
              </Button>
            </CardContent>
          </Card>

          {single.data && (
            <Card className={`border ${single.data.result.prediction === "genuine"
              ? "border-emerald-500/40 bg-emerald-950/20" : single.data.result.prediction === "suspicious"
              ? "border-red-500/40 bg-red-950/20" : "border-amber-500/40 bg-amber-950/20"}`}
                  data-testid="seed-result">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="uppercase" data-testid="seed-prediction">{single.data.result.prediction}</span>
                  <span className="font-mono" data-testid="seed-confidence">
                    {Math.round(single.data.result.confidence * 100)}%
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="h-2 rounded-full bg-[#0B130E] overflow-hidden">
                  <div className={`h-full ${single.data.result.prediction === "genuine" ? "bg-emerald-400" : "bg-red-400"}`}
                       style={{ width: `${single.data.result.confidence * 100}%` }} />
                </div>
                <p className="text-sm text-emerald-100/85">{single.data.result.reasoning}</p>
                {!!single.data.result.defects?.length && (
                  <div className="flex flex-wrap gap-1">
                    {single.data.result.defects.map((d, i) => (
                      <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded border border-red-500/40 text-red-300">{d}</span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="batch" className="pt-4 space-y-4">
          <Card className="bg-card border-[#1E3A2B]">
            <CardContent className="py-4 space-y-3">
              <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-[#1E3A2B] text-sm cursor-pointer hover:border-emerald-500/50">
                <Upload className="w-4 h-4" /> Add seeds to tray ({batch.length}/24)
                <input type="file" accept="image/jpeg,image/png,image/webp" hidden multiple
                       data-testid="seed-batch-input"
                       onChange={(e) => {
                         Array.from(e.target.files ?? []).slice(0, 24 - batch.length).forEach((f) =>
                           read(f, (s) => setBatch((p) => [...p, s.split(",")[1]])));
                       }} />
              </label>
              <Button onClick={() => batchRun.mutate()} disabled={!batch.length || batchRun.isPending}
                      data-testid="seed-batch-analyze-btn">
                {batchRun.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Zap className="w-4 h-4 mr-2" />}
                Analyze batch ({batch.length})
              </Button>
            </CardContent>
          </Card>

          {batchRun.data && (
            <Card className="bg-card border-[#1E3A2B]" data-testid="seed-batch-result">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  <span>Batch verdict: <b className="uppercase" data-testid="batch-verdict">{batchRun.data.summary.verdict}</b></span>
                  <span className="font-mono text-emerald-400" data-testid="batch-score">
                    {batchRun.data.summary.genuineness_score}/100
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-4 sm:grid-cols-8 gap-2">
                {batchRun.data.items.map((it) => (
                  <div key={it.index} className="text-center">
                    {it.thumb_b64 && (
                      <img src={`data:image/jpeg;base64,${it.thumb_b64}`} alt={`seed ${it.index}`}
                           className={`w-full aspect-square object-cover rounded border ${
                             it.result.prediction === "genuine" ? "border-emerald-500/60" : "border-red-500/60"}`} />
                    )}
                    <div className="text-[9px] font-mono text-muted-foreground mt-0.5">
                      {it.result.prediction.slice(0, 4)} {Math.round(it.result.confidence * 100)}%
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
