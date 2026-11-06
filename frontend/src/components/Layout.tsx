import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router";
import { canRead, useAuth } from "../session";
import { CloseIcon, LogoMark, MenuIcon } from "./icons";
import { SearchBox } from "./SearchBox";
import { TourButton, TourInvite, TourProvider } from "./Tour";
import { NotificationBell, UserMenu } from "./TopBarMenus";
import { useHashFocus } from "./useHashFocus";

const pill = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3.5 py-1.5 text-sm whitespace-nowrap transition ${
    isActive
      ? "bg-accent-purple/20 text-white"
      : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
  }`;

export function Layout() {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  useHashFocus();
  if (!user) return null;

  const leader = user.role !== "employee";
  const links = [
    { to: "/dashboard", text: "Dashboard", show: leader },
    { to: "/sales", text: "Sales", show: canRead(user, "sales") },
    { to: "/payments", text: "Payments", show: canRead(user, "finance") },
    { to: "/hr", text: "Hiring", show: canRead(user, "hr") },
    { to: "/support", text: "Support", show: canRead(user, "support") },
    { to: "/procurement", text: "Procurement", show: canRead(user, "procurement") },
    { to: "/approvals", text: "Approvals", show: true },
    { to: "/activity", text: "Command Center", show: true },
  ].filter((l) => l.show);
  const closeMenu = () => setMenuOpen(false);

  return (
    <TourProvider>
      <div className="min-h-screen">
        <header className="sticky top-0 z-40 border-b border-white/5 bg-navy-950/85 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-2 px-4 md:gap-3 md:px-6">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              className="grid h-9 w-9 place-items-center rounded-lg text-slate-300 hover:bg-white/5 xl:hidden"
            >
              {menuOpen ? <CloseIcon /> : <MenuIcon />}
            </button>
            <Link to="/" className="flex shrink-0 items-center gap-2" onClick={closeMenu}>
              <LogoMark />
              <span className="text-[15px] font-bold text-white">
                UNIFY <span className="font-medium text-slate-400">SUITE</span>
              </span>
            </Link>
            <nav aria-label="Main" className="ml-4 hidden items-center gap-1 xl:flex">
              {links.map((l) => (
                <NavLink key={l.to} to={l.to} className={pill}>
                  {l.text}
                </NavLink>
              ))}
            </nav>
            <div className="flex-1" />
            <div className="hidden w-56 md:block 2xl:w-72">
              <SearchBox />
            </div>
            <TourButton />
            <NotificationBell key={user.id} />
            <UserMenu />
          </div>
          {menuOpen && (
            <div className="border-t border-white/5 px-4 pt-3 pb-4 xl:hidden">
              <div className="mb-3 md:hidden">
                <SearchBox onNavigate={closeMenu} />
              </div>
              <nav aria-label="Main" className="grid grid-cols-2 gap-1 sm:grid-cols-4">
                {links.map((l) => (
                  <NavLink key={l.to} to={l.to} className={pill} onClick={closeMenu}>
                    {l.text}
                  </NavLink>
                ))}
              </nav>
            </div>
          )}
        </header>
        {/* Keyed by user: after a demo role switch every page reloads its data as the new user. */}
        <main key={user.id} className="mx-auto max-w-[1600px] px-4 py-6 md:px-6">
          <Outlet />
        </main>
        <TourInvite />
      </div>
    </TourProvider>
  );
}
