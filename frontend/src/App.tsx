import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AuthProvider } from "./auth";
import { canRead, useAuth } from "./session";
import { Layout } from "./components/Layout";
import { Activity } from "./pages/Activity";
import { Approvals } from "./pages/Approvals";
import { Hiring } from "./pages/Hiring";
import { Login } from "./pages/Login";
import { PaymentRun } from "./pages/PaymentRun";
import { Payments } from "./pages/Payments";
import { Sales } from "./pages/Sales";
import type { Department } from "./types";

const DEPARTMENT_HOME: Partial<Record<Department, string>> = {
  sales: "/sales",
  hr: "/hr",
  finance: "/payments",
};

function RequireUser({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-8 text-slate-500">Loading…</p>;
  return user ? children : <Navigate to="/login" replace />;
}

/** Land people on their own department's page; everyone else on the Approval Center. */
function Home() {
  const { user } = useAuth();
  const own = user && user.role !== "executive" ? DEPARTMENT_HOME[user.department] : undefined;
  if (own) return <Navigate to={own} replace />;
  return <Navigate to={user && canRead(user, "finance") ? "/payments" : "/approvals"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
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
            <Route path="payments" element={<Payments />} />
            <Route path="payments/:id" element={<PaymentRun />} />
            <Route path="sales" element={<Sales />} />
            <Route path="hr" element={<Hiring />} />
            <Route path="approvals" element={<Approvals />} />
            <Route path="activity" element={<Activity />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
