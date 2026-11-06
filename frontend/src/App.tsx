import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AuthProvider } from "./auth";
import { canRead, useAuth } from "./session";
import { Layout } from "./components/Layout";
import { Toaster } from "./components/Toaster";
import { Activity } from "./pages/Activity";
import { Approvals } from "./pages/Approvals";
import { Hiring } from "./pages/Hiring";
import { Login } from "./pages/Login";
import { PaymentRun } from "./pages/PaymentRun";
import { Procurement } from "./pages/Procurement";
import { Payments } from "./pages/Payments";
import { Sales } from "./pages/Sales";
import { Support } from "./pages/Support";
import type { Department } from "./types";

// The dashboard brings the chart library; load it only when someone opens the dashboard.
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));

const DEPARTMENT_HOME: Partial<Record<Department, string>> = {
  sales: "/sales",
  hr: "/hr",
  finance: "/payments",
  support: "/support",
  procurement: "/procurement",
};

function RequireUser({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-8 text-slate-500">Loading…</p>;
  return user ? children : <Navigate to="/login" replace />;
}

/** Land people on their own department's page; everyone else on the Approval Center. */
function Home() {
  const { user } = useAuth();
  if (user && user.role !== "employee") return <Navigate to="/dashboard" replace />;
  const own = user ? DEPARTMENT_HOME[user.department] : undefined;
  if (own) return <Navigate to={own} replace />;
  return <Navigate to={user && canRead(user, "finance") ? "/payments" : "/approvals"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <Toaster>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              element={
                <RequireUser>
                  <Layout />
                </RequireUser>
              }
            >
              <Route index element={<Home />} />
              <Route
                path="dashboard"
                element={
                  <Suspense fallback={<p className="text-slate-500">Loading…</p>}>
                    <Dashboard />
                  </Suspense>
                }
              />
              <Route path="payments" element={<Payments />} />
              <Route path="payments/:id" element={<PaymentRun />} />
              <Route path="sales" element={<Sales />} />
              <Route path="hr" element={<Hiring />} />
              <Route path="support" element={<Support />} />
              <Route path="procurement" element={<Procurement />} />
              <Route path="approvals" element={<Approvals />} />
              <Route path="activity" element={<Activity />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </Toaster>
    </AuthProvider>
  );
}
