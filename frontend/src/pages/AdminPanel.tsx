import { useQuery } from "@tanstack/react-query";
import { Loader2, ShieldAlert } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Stat } from "@/components/analysis/Primitives";
import { apiGet } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AdminOverview, User } from "@/lib/types";

export default function AdminPanel() {
  const { user } = useSession();
  const isAdmin = user?.role === "ADMIN";

  const { data, isLoading, isError } = useQuery<AdminOverview>({
    queryKey: ["admin-overview"], queryFn: () => apiGet<AdminOverview>("/admin/overview"),
    enabled: isAdmin, retry: false,
  });
  const { data: users } = useQuery<(User & { field_count: number; analysis_count: number })[]>({
    queryKey: ["admin-users"],
    queryFn: () => apiGet<(User & { field_count: number; analysis_count: number })[]>("/admin/users"),
    enabled: isAdmin, retry: false,
  });

  if (!isAdmin) {
    return (
      <div className="max-w-xl mx-auto p-6" data-testid="admin-forbidden">
        <Card className="bg-card border-red-500/30">
          <CardContent className="py-6 flex gap-3 items-start">
            <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold">Admin access required</div>
              <p className="text-sm text-muted-foreground mt-1">
                Your role is {user?.role ?? "unknown"}. System-level analytics are restricted to ADMIN accounts.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-[1600px] mx-auto p-4 sm:p-6 space-y-5" data-testid="admin-panel-page">
      <div>
        <h1 className="text-3xl font-bold">Admin panel</h1>
        <p className="text-sm text-muted-foreground mt-1">Platform-wide usage, flood events and monitoring jobs.</p>
      </div>

      {isLoading && <Loader2 className="w-5 h-5 animate-spin text-emerald-400" />}
      {isError && <p className="text-sm text-amber-300">Admin analytics unavailable right now.</p>}

      {data && (
        <>
          <section className="grid grid-cols-2 lg:grid-cols-6 gap-3" data-testid="admin-counts">
            {Object.entries(data.counts).map(([k, v]) => (
              <Stat key={k} label={k.replace(/_/g, " ")} value={v} testid={`admin-count-${k}`} />
            ))}
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="bg-card border-[#1E3A2B]" data-testid="admin-analyses-chart">
              <CardHeader className="pb-2"><CardTitle className="text-base">Analyses over time</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={data.analyses_over_time}>
                    <CartesianGrid stroke="#1E3A2B" strokeDasharray="3 3" />
                    <XAxis dataKey="month" stroke="#9CA3AF" fontSize={11} />
                    <YAxis stroke="#9CA3AF" fontSize={11} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: "#121F18", border: "1px solid #1E3A2B", borderRadius: 8 }} />
                    <Line type="monotone" dataKey="count" stroke="#10B981" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="bg-card border-[#1E3A2B]" data-testid="admin-severity-chart">
              <CardHeader className="pb-2"><CardTitle className="text-base">Flood severity distribution</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={data.flood_severity}>
                    <CartesianGrid stroke="#1E3A2B" strokeDasharray="3 3" />
                    <XAxis dataKey="severity" stroke="#9CA3AF" fontSize={11} />
                    <YAxis stroke="#9CA3AF" fontSize={11} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: "#121F18", border: "1px solid #1E3A2B", borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#06B6D4" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </section>

          <Card className="bg-card border-[#1E3A2B] p-0 overflow-hidden" data-testid="admin-users-table">
            <Table>
              <TableHeader>
                <TableRow><TableHead>User</TableHead><TableHead>Role</TableHead>
                <TableHead>Fields</TableHead><TableHead>Analyses</TableHead><TableHead>Joined</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {users?.map((u) => (
                  <TableRow key={u.id} data-testid={`admin-user-${u.id}`}>
                    <TableCell className="text-xs">{u.email}</TableCell>
                    <TableCell className="text-xs font-mono">{u.role}</TableCell>
                    <TableCell className="text-xs font-mono">{u.field_count}</TableCell>
                    <TableCell className="text-xs font-mono">{u.analysis_count}</TableCell>
                    <TableCell className="text-xs font-mono">
                      {(u as unknown as { created_at?: string }).created_at?.slice(0, 10)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          {data.recent_errors.length > 0 && (
            <Card className="bg-card border-[#1E3A2B]" data-testid="admin-errors">
              <CardHeader className="pb-2"><CardTitle className="text-base">Recent analysis errors</CardTitle></CardHeader>
              <CardContent className="space-y-1 text-xs font-mono text-amber-300">
                {data.recent_errors.map((e, i) => (
                  <div key={i}>{e.created_at?.slice(0, 16).replace("T", " ")} — {JSON.stringify(e.detail)}</div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
