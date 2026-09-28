import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Shield, Satellite, Droplets, Sprout } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiPost } from "@/lib/api";
import { beginSession } from "@/lib/session";
import type { TokenOut } from "@/lib/types";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, name };
      return apiPost<TokenOut>(path, body);
    },
    onSuccess: async (data) => {
      await beginSession();
      toast.success(mode === "login" ? `Welcome back, ${data.user.name}` : "Account created");
      nav("/app/dashboard", { replace: true });
    },
    onError: (e: unknown) => {
      const body = (e as { body?: { detail?: unknown } }).body;
      const detail = body?.detail;
      toast.error(
        typeof detail === "string" ? detail
          : Array.isArray(detail) ? String((detail[0] as { msg?: string })?.msg ?? "Invalid input")
          : "Could not sign in",
      );
    },
  });

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Mission panel */}
      <div className="relative hidden lg:flex flex-col justify-between p-10 overflow-hidden border-r border-[#1E3A2B]">
        <div className="absolute inset-0 radar-grid" />
        <div className="absolute inset-0 tactical-scanlines" />
        <div className="absolute -right-32 top-1/4 w-[420px] h-[420px] rounded-full border border-emerald-500/20">
          <div className="radar-sweep w-full h-full rounded-full"
               style={{ background: "conic-gradient(from 0deg, rgba(16,185,129,0.22), transparent 38%)" }} />
        </div>
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-emerald-500/15 border border-emerald-500/40 grid place-items-center">
              <Shield className="w-6 h-6 text-emerald-400" />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight">AgriGaurd</div>
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                Satellite · Flood · Crop Intelligence
              </div>
            </div>
          </div>
        </div>
        <div className="relative space-y-6 max-w-md">
          <h1 className="text-4xl font-bold leading-tight">
            AI-powered satellite flood monitoring, land suitability and crop intelligence
          </h1>
          <p className="text-muted-foreground text-sm">
            Sentinel-1 SAR change detection with permanent-water removal, cropland masking, Copernicus DEM
            terrain context, SoilGrids soil profiling and Open-Meteo rainfall — every result explained by
            the evidence behind it.
          </p>
          <div className="grid gap-3">
            {[
              { icon: Satellite, text: "Latest available satellite observation — never called live" },
              { icon: Droplets, text: "Agricultural flood % separated from total water %" },
              { icon: Sprout, text: "Explainable crop recommendations from agronomic ranges" },
            ].map((f, i) => (
              <div key={i} className="flex items-center gap-3 text-sm text-emerald-100/85">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/25 grid place-items-center shrink-0">
                  <f.icon className="w-4 h-4 text-emerald-400" />
                </div>
                {f.text}
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-[10px] text-muted-foreground font-mono">
          Remote-sensing based estimates · Decision support only · Field verification recommended
        </p>
      </div>

      {/* Form */}
      <div className="flex items-center justify-center p-6 sm:p-10">
        <form
          data-testid="auth-form"
          onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}
          className="w-full max-w-sm space-y-5"
        >
          <div className="lg:hidden flex items-center gap-2.5 mb-2">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/40 grid place-items-center">
              <Shield className="w-5 h-5 text-emerald-400" />
            </div>
            <span className="text-xl font-bold">AgriGaurd</span>
          </div>

          <div>
            <h2 className="text-2xl font-bold">{mode === "login" ? "Sign in" : "Create your account"}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {mode === "login" ? "Access your fields, analyses and alerts" : "Start monitoring your farm in minutes"}
            </p>
          </div>

          {mode === "register" && (
            <div className="space-y-1.5">
              <Label htmlFor="name">Full name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required
                     data-testid="auth-name-input" placeholder="Your name" />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                   data-testid="auth-email-input" placeholder="you@example.com" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   required minLength={8} data-testid="auth-password-input"
                   placeholder={mode === "register" ? "8+ chars, a letter and a number" : "••••••••"} />
          </div>

          <Button type="submit" disabled={mutation.isPending} data-testid="auth-submit-btn" className="w-full">
            {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>

          <p className="text-sm text-center text-muted-foreground">
            {mode === "login" ? (
              <>New to AgriGaurd?{" "}
                <Link to="/register" className="text-emerald-400 hover:underline" data-testid="auth-switch-register">
                  Create an account
                </Link>
              </>
            ) : (
              <>Already registered?{" "}
                <Link to="/login" className="text-emerald-400 hover:underline" data-testid="auth-switch-login">
                  Sign in
                </Link>
              </>
            )}
          </p>
        </form>
      </div>
    </div>
  );
}
