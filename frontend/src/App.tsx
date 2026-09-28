import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Navbar from "@/components/layout/Navbar";
import { useSession } from "@/lib/session";
import AuthPage from "@/pages/AuthPage";
import Dashboard from "@/pages/Dashboard";
import Fields from "@/pages/Fields";
import FieldDetail from "@/pages/FieldDetail";
import Analyze from "@/pages/Analyze";
import AnalysisResult from "@/pages/AnalysisResult";
import Notifications from "@/pages/Notifications";
import SystemHealth from "@/pages/SystemHealth";
import AdminPanel from "@/pages/AdminPanel";
import SeedAI from "@/pages/SeedAI";
import CropLibrary from "@/pages/CropLibrary";
import { Loader2 } from "lucide-react";

function Protected() {
  const { user, loading } = useSession();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center" data-testid="session-loading">
        <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return (
    <div className="min-h-screen">
      <Navbar />
      <Outlet />
    </div>
  );
}

function Landing() {
  const { user, loading } = useSession();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center">
        <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
      </div>
    );
  }
  return <Navigate to={user ? "/app/dashboard" : "/login"} replace />;
}

export default function App() {
  return (
    <>
      <Toaster richColors />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="/app" element={<Protected />}>
          <Route index element={<Navigate to="/app/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="fields" element={<Fields />} />
          <Route path="fields/:fieldId" element={<FieldDetail />} />
          <Route path="analyze" element={<Analyze />} />
          <Route path="analyses/:analysisId" element={<AnalysisResult />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="health" element={<SystemHealth />} />
          <Route path="admin" element={<AdminPanel />} />
          <Route path="seed-ai" element={<SeedAI />} />
          <Route path="crops" element={<CropLibrary />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
