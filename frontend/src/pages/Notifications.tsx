import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bell, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiGet, apiPost } from "@/lib/api";
import type { NotificationDoc } from "@/lib/types";

const VIEWS = [
  { v: "all", l: "All" }, { v: "unread", l: "Unread" },
  { v: "critical", l: "Critical" }, { v: "information", l: "Information" },
];

export default function Notifications() {
  const qc = useQueryClient();
  const [view, setView] = useState("all");
  const { data, isLoading } = useQuery<NotificationDoc[]>({
    queryKey: ["notifications", view],
    queryFn: () => apiGet<NotificationDoc[]>(`/notifications?view=${view}`), retry: false,
  });
  const read = useMutation({
    mutationFn: (id: string) => apiPost(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readAll = useMutation({
    mutationFn: () => apiPost("/notifications/read-all"),
    onSuccess: () => { toast.success("All marked read"); qc.invalidateQueries({ queryKey: ["notifications"] }); },
  });

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-4" data-testid="notifications-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold">Notification centre</h1>
          <p className="text-sm text-muted-foreground mt-1">Flood alerts, monitoring scans and system messages.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => readAll.mutate()} data-testid="mark-all-read-btn">
          Mark all read
        </Button>
      </div>

      <Tabs value={view} onValueChange={setView}>
        <TabsList variant="line" data-testid="notification-tabs">
          {VIEWS.map((v) => <TabsTrigger key={v.v} value={v.v} data-testid={`notif-tab-${v.v}`}>{v.l}</TabsTrigger>)}
        </TabsList>
      </Tabs>

      {isLoading && <Loader2 className="w-5 h-5 animate-spin text-emerald-400" />}
      {!isLoading && !data?.length && (
        <p className="text-sm text-muted-foreground py-8 text-center" data-testid="notifications-empty">
          Nothing here yet.
        </p>
      )}
      <div className="space-y-2">
        {data?.map((n) => (
          <Card key={n.id} className={`border-[#1E3A2B] ${n.read ? "bg-card/60" : "bg-card"}`}
                data-testid={`notification-${n.id}`}>
            <CardContent className="py-3 flex items-start gap-3">
              <Bell className={`w-4 h-4 shrink-0 mt-0.5 ${
                ["high", "critical"].includes(n.severity) ? "text-red-400" : "text-emerald-400"}`} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{n.title}</div>
                <div className="text-xs text-muted-foreground">{n.body}</div>
                <div className="text-[10px] font-mono text-muted-foreground mt-1">
                  {n.severity} · {n.created_at?.slice(0, 16).replace("T", " ")}
                </div>
              </div>
              {!n.read && (
                <Button size="xs" variant="ghost" onClick={() => read.mutate(n.id)}
                        data-testid={`notif-read-${n.id}`}><Check className="w-3.5 h-3.5" /></Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
