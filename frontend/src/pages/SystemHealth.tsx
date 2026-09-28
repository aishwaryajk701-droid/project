import { useQuery } from "@tanstack/react-query";
import { Activity, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/api";
import type { HealthOut } from "@/lib/types";

const COLORS: Record<string, string> = {
  CONNECTED: "text-emerald-400 border-emerald-500/40 bg-emerald-950/40",
  "NOT CONFIGURED": "text-amber-400 border-amber-500/40 bg-amber-950/40",
  ERROR: "text-red-400 border-red-500/40 bg-red-950/40",
  OPTIONAL: "text-cyan-400 border-cyan-500/40 bg-cyan-950/40",
};

export default function SystemHealth() {
  const { data, isLoading } = useQuery<HealthOut>({
    queryKey: ["health"], queryFn: () => apiGet<HealthOut>("/health"),
    refetchInterval: 120_000, retry: false,
  });

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-4" data-testid="system-health-page">
      <div>
        <h1 className="text-3xl font-bold">System health</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Live connectivity probes for every data source. Credentials are never displayed.
        </p>
      </div>

      {isLoading && <Loader2 className="w-5 h-5 animate-spin text-emerald-400" />}

      {data && (
        <Card className="bg-card border-[#1E3A2B]">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" /> Services
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between py-1.5 border-b border-[#1E3A2B]"
                 data-testid="health-backend">
              <span className="text-sm">Backend API</span>
              <span className={`px-2 py-0.5 rounded-md border text-[10px] font-mono ${COLORS.CONNECTED}`}>
                CONNECTED
              </span>
            </div>
            {data.checks.map((c) => (
              <div key={c.service} className="flex items-center justify-between py-1.5 border-b border-[#1E3A2B] last:border-0 gap-3"
                   data-testid={`health-${c.service.replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase()}`}>
                <div className="min-w-0">
                  <div className="text-sm">{c.service}</div>
                  <div className="text-[10px] text-muted-foreground truncate">{c.detail}</div>
                </div>
                <span className={`px-2 py-0.5 rounded-md border text-[10px] font-mono whitespace-nowrap ${COLORS[c.status]}`}>
                  {c.status}
                </span>
              </div>
            ))}
            <p className="text-[11px] text-muted-foreground pt-2">{data.note}</p>
            <p className="text-[10px] font-mono text-muted-foreground">Checked {data.checked_at?.slice(0, 19).replace("T", " ")} UTC</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
