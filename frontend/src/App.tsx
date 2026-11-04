import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AuthProvider } from "./auth";
import { canRead, useAuth } from "./session";
import { Layout } from "./components/Layout";
import { Activity } from "./pages/Activity";
import { Approvals } from "./pages/Approvals";
import { Login } from "./pages/Login";
import { PaymentRun } from "./pages/PaymentRun";
import { Payments } from "./pages/Payments";
import { Sales } from "./pages/Sales";

function RequireUser({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-8 text-slate-500">Loading…</p>;
  return user ? children : <Navigate to="/login" replace />;
}

function Home() {
  const { user } = useAuth();
  if (user && canRead(user, "sales") && user.department === "sales")
    return <Navigate to="/sales" replace />;
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
            <Route path="approvals" element={<Approvals />} />
            <Route path="activity" element={<Activity />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
