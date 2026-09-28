import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bell, Check, Loader2, Mail, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import type { AlertPrefs, NotificationDoc } from "@/lib/types";

const SEVERITIES = ["low", "moderate", "high", "critical"];

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

  const { data: prefs } = useQuery<AlertPrefs>({
    queryKey: ["alert-prefs"], queryFn: () => apiGet<AlertPrefs>("/alerts/preferences"), retry: false,
  });
  const [draft, setDraft] = useState<AlertPrefs | null>(null);
  const p = draft ?? prefs ?? null;
  const savePrefs = useMutation({
    mutationFn: (v: AlertPrefs) => apiPut<AlertPrefs>("/alerts/preferences", v),
    onSuccess: () => { toast.success("Alert preferences saved"); qc.invalidateQueries({ queryKey: ["alert-prefs"] }); },
    onError: () => toast.error("Could not save alert preferences"),
  });
  const testAlert = useMutation({
    mutationFn: () => apiPost("/alerts/test"),
    onSuccess: () => toast.success("Test alert sent — check your inbox"),
    onError: (e: unknown) => {
      const detail = (e as { body?: { detail?: string } }).body?.detail;
      toast.error(typeof detail === "string" ? detail : "Could not send the test alert");
    },
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

      {p && (
        <Card className="bg-card border-[#1E3A2B]" data-testid="alert-prefs-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Daily flood alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Every monitored field is re-scanned each morning. When new water appears you get an
              in-app alert plus the channels you enable here — always with the real evidence behind
              the result.
            </p>

            <div className="flex flex-wrap gap-6 items-end">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox id="email-on" checked={p.email_enabled} data-testid="alert-email-toggle"
                            onCheckedChange={(v: boolean) => setDraft({ ...p, email_enabled: !!v })} />
                  <Label htmlFor="email-on" className="flex items-center gap-1.5 cursor-pointer">
                    <Mail className="w-3.5 h-3.5 text-emerald-400" /> Email alerts
                  </Label>
                </div>
                <Input value={p.alert_email ?? ""} placeholder="you@example.com"
                       data-testid="alert-email-input" className="w-64"
                       onChange={(e) => setDraft({ ...p, alert_email: e.target.value })} />
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox id="sms-on" checked={p.sms_enabled} data-testid="alert-sms-toggle"
                            onCheckedChange={(v: boolean) => setDraft({ ...p, sms_enabled: !!v })} />
                  <Label htmlFor="sms-on" className="flex items-center gap-1.5 cursor-pointer">
                    <MessageSquare className="w-3.5 h-3.5 text-sky-400" /> SMS alerts (needs Twilio)
                  </Label>
                </div>
                <Input value={p.alert_phone ?? ""} placeholder="+91XXXXXXXXXX"
                       data-testid="alert-phone-input" className="w-56"
                       onChange={(e) => setDraft({ ...p, alert_phone: e.target.value })} />
              </div>

              <div className="space-y-2">
                <Label>Minimum severity</Label>
                <Select value={p.min_severity}
                        onValueChange={(v: string) => setDraft({ ...p, min_severity: v })}>
                  <SelectTrigger data-testid="alert-severity-select" className="w-40">
                    <SelectValue>{(v) => String(v)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex gap-2">
              <Button size="sm" data-testid="alert-prefs-save-btn"
                      disabled={savePrefs.isPending} onClick={() => savePrefs.mutate(p)}>
                {savePrefs.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Save preferences
              </Button>
              <Button size="sm" variant="secondary" data-testid="alert-test-btn"
                      disabled={testAlert.isPending} onClick={() => testAlert.mutate()}>
                Send test alert
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

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
