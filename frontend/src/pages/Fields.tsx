import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Loader2, Radar, Trash2, Pencil, Search, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import type { FieldDoc } from "@/lib/types";

export default function Fields() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<FieldDoc | null>(null);
  const [editName, setEditName] = useState("");

  const { data: fields, isLoading } = useQuery<FieldDoc[]>({
    queryKey: ["fields"], queryFn: () => apiGet<FieldDoc[]>("/fields"), retry: false,
  });

  const analyze = useMutation({
    mutationFn: (id: string) => apiPost<{ job_id: string }>(`/fields/${id}/analyze`),
    onSuccess: () => { toast.success("Analysis started — track it on the field page"); qc.invalidateQueries({ queryKey: ["fields"] }); },
    onError: () => toast.error("Could not start the analysis"),
  });
  const del = useMutation({
    mutationFn: (id: string) => apiDelete(`/fields/${id}`),
    onSuccess: () => { toast.success("Field deleted"); qc.invalidateQueries({ queryKey: ["fields"] }); },
  });
  const rename = useMutation({
    mutationFn: () => apiPatch<FieldDoc>(`/fields/${editing!.id}`, { name: editName }),
    onSuccess: () => { toast.success("Field updated"); setEditing(null); qc.invalidateQueries({ queryKey: ["fields"] }); },
  });

  const list = (fields ?? []).filter((f) =>
    !q || [f.name, f.state, f.district, f.village].filter(Boolean).join(" ").toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="max-w-[1800px] mx-auto p-4 sm:p-6 space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">My fields</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Every saved farm boundary with its latest flood status, confidence, suitability and crop.
          </p>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search fields or locations"
                   data-testid="fields-search-input" className="pl-8 w-56" />
          </div>
          <Link to="/app/analyze"><Button data-testid="fields-new-btn"><Radar className="w-4 h-4 mr-2" />New field / analysis</Button></Link>
        </div>
      </div>

      <Card className="bg-card border-[#1E3A2B] overflow-hidden p-0" data-testid="fields-table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Field</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Area</TableHead>
              <TableHead>Flood</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Suitability</TableHead>
              <TableHead>Crop</TableHead>
              <TableHead>Monitoring</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={9} className="text-center py-10">
                <Loader2 className="w-5 h-5 animate-spin text-emerald-400 mx-auto" />
              </TableCell></TableRow>
            )}
            {!isLoading && !list.length && (
              <TableRow><TableCell colSpan={9} className="text-center py-10 text-muted-foreground"
                                   data-testid="fields-empty">
                No fields yet — run an analysis and tick "Save this boundary to My Fields".
              </TableCell></TableRow>
            )}
            {list.map((f) => (
              <TableRow key={f.id} data-testid={`field-row-${f.id}`}>
                <TableCell className="font-medium">{f.name}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {[f.village, f.district, f.state].filter(Boolean).join(", ") || "—"}
                </TableCell>
                <TableCell className="font-mono text-xs">{f.area_ha} ha</TableCell>
                <TableCell>
                  {f.flood_pct == null ? <span className="text-xs text-muted-foreground">not analysed</span>
                    : <Badge variant="outline" className={(f.flood_pct ?? 0) >= 10
                        ? "border-red-500/40 text-red-300" : "border-emerald-500/40 text-emerald-300"}>
                        {f.flood_pct}%
                      </Badge>}
                </TableCell>
                <TableCell className="font-mono text-xs">{f.flood_confidence ?? "—"}</TableCell>
                <TableCell className="font-mono text-xs">{f.land_suitability ?? "—"}</TableCell>
                <TableCell className="text-xs">{f.recommended_crop ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant={f.monitoring?.enabled ? "default" : "secondary"} className="text-[10px]">
                    {f.monitoring?.enabled ? f.monitoring.frequency.replace(/_/g, " ") : "off"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button size="xs" variant="ghost" onClick={() => nav(`/app/fields/${f.id}`)}
                          data-testid={`field-view-${f.id}`}><Eye className="w-3.5 h-3.5" /></Button>
                  <Button size="xs" variant="ghost" onClick={() => analyze.mutate(f.id)}
                          disabled={analyze.isPending} data-testid={`field-analyze-${f.id}`}>
                    <Radar className="w-3.5 h-3.5" />
                  </Button>
                  <Button size="xs" variant="ghost" data-testid={`field-report-${f.id}`}
                          onClick={() => window.open(`/api/reports/fields/${f.id}/report.pdf`, "_blank")}>
                    <FileText className="w-3.5 h-3.5" />
                  </Button>
                  <Button size="xs" variant="ghost" onClick={() => { setEditing(f); setEditName(f.name); }}
                          data-testid={`field-edit-${f.id}`}><Pencil className="w-3.5 h-3.5" /></Button>
                  <Button size="xs" variant="ghost" className="text-red-400"
                          onClick={() => del.mutate(f.id)} data-testid={`field-delete-${f.id}`}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent data-testid="field-edit-dialog">
          <DialogHeader><DialogTitle>Rename field</DialogTitle></DialogHeader>
          <Input value={editName} onChange={(e) => setEditName(e.target.value)} data-testid="field-edit-name-input" />
          <DialogFooter>
            <Button onClick={() => rename.mutate()} disabled={rename.isPending} data-testid="field-edit-save-btn">
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
