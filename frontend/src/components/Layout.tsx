import { NavLink, Outlet } from "react-router";
import { canRead, useAuth } from "../session";
import { label } from "../format";

export function Layout() {
  const { user, signOut } = useAuth();
  if (!user) return null;

  const links = [
    { to: "/payments", text: "Supplier payments", show: canRead(user, "finance") },
    { to: "/approvals", text: "Approval Center", show: true },
    { to: "/activity", text: "Agent activity", show: true },
  ].filter((l) => l.show);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-navy-800 bg-navy-900 md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="px-5 py-5">
          <span className="bg-gradient-to-r from-accent-purple to-accent-cyan bg-clip-text text-lg font-bold tracking-tight text-transparent">
            UNIFY SUITE
          </span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm whitespace-nowrap ${
                  isActive
                    ? "bg-accent-purple/20 text-white"
                    : "text-slate-400 hover:bg-navy-800 hover:text-slate-200"
                }`
              }
            >
              {l.text}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b border-navy-800 px-4 py-3 md:px-8">
          <div className="text-right text-sm">
            <div className="text-slate-200">{user.full_name}</div>
            <div className="text-xs text-slate-500">
              {label(user.role)} · {user.department}
            </div>
          </div>
          <button onClick={signOut} className="text-sm text-slate-400 hover:text-white">
            Sign out
          </button>
        </header>
        <main className="flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
