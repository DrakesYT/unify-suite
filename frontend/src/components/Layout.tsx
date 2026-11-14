import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { canRead, useAuth } from "../session";
import {
  BoltIcon,
  CartIcon,
  ChartIcon,
  CloseIcon,
  GridIcon,
  LogoMark,
  MenuIcon,
  ShieldIcon,
  TicketIcon,
  UsersIcon,
  WalletIcon,
} from "./icons";
import { AuraDock } from "./AuraDock";
import { SearchBox } from "./SearchBox";
import { ThemeSwitch } from "./ThemeSwitch";
import { TourButton, TourInvite, TourProvider } from "./Tour";
import { NotificationBell, UserMenu } from "./TopBarMenus";
import { useHashFocus } from "./useHashFocus";

const PAGE_TITLES: [string, string][] = [
  ["/dashboard", "Dashboard"],
  ["/sales", "Sales"],
  ["/payments", "Payments"],
  ["/hr", "Hiring"],
  ["/support", "Support"],
  ["/procurement", "Procurement"],
  ["/approvals", "Approvals"],
  ["/activity", "Command Center"],
  ["/users", "Users"],
  ["/account", "Account"],
];

interface NavItem {
  to: string;
  text: string;
  icon: ReactNode;
}

const pill = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm whitespace-nowrap transition-colors duration-150 ${
    isActive
      ? "bg-accent-purple/15 font-medium text-white"
      : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
  }`;

/** The floating icon rail on the left (desktop): white tile for the open page, label on hover. */
function SideRail({ links }: { links: NavItem[] }) {
  return (
    <aside
      data-theme="dark"
      className="sticky top-20 z-30 hidden h-fit max-h-[calc(100vh-6rem)] w-[68px] shrink-0 flex-col items-center gap-1.5 rounded-r-[28px] bg-gradient-to-b from-[var(--rail-from)] to-[var(--rail-to)] py-4 shadow-xl shadow-[rgb(79_53_214/0.35)] md:flex"
    >
      <nav aria-label="Main" className="flex flex-col items-center gap-1.5">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            aria-label={l.text}
            className={({ isActive }) =>
              `rail-item relative grid h-11 w-11 place-items-center rounded-2xl transition-colors duration-150 ${
                isActive
                  ? "bg-[#fff] text-[#5b3fd6] shadow-lg shadow-[rgb(30_16_90/0.35)]"
                  : "text-white/80 hover:bg-white/15 hover:text-white"
              }`
            }
          >
            {l.icon}
            <span className="rail-tip pointer-events-none absolute left-[calc(100%+12px)] rounded-lg bg-[#17142e] px-2.5 py-1 text-xs font-medium whitespace-nowrap text-[#fff] shadow-lg">
              {l.text}
            </span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

export function Layout() {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  useHashFocus();
  useEffect(() => {
    // The tab says which page it is, so several open tabs can be told apart.
    const page = PAGE_TITLES.find(([prefix]) => pathname.startsWith(prefix))?.[1];
    document.title = page ? `${page} · UNIFY SUITE` : "UNIFY SUITE";
    return () => {
      document.title = "UNIFY SUITE";
    };
  }, [pathname]);
  if (!user) return null;

  const leader = user.role !== "employee";
  const links: NavItem[] = [
    { to: "/dashboard", text: "Dashboard", show: leader, icon: <GridIcon size={19} /> },
    { to: "/sales", text: "Sales", show: canRead(user, "sales"), icon: <ChartIcon size={19} /> },
    {
      to: "/payments",
      text: "Payments",
      show: canRead(user, "finance"),
      icon: <WalletIcon size={19} />,
    },
    { to: "/hr", text: "Hiring", show: canRead(user, "hr"), icon: <UsersIcon size={19} /> },
    {
      to: "/support",
      text: "Support",
      show: canRead(user, "support"),
      icon: <TicketIcon size={19} />,
    },
    {
      to: "/procurement",
      text: "Procurement",
      show: canRead(user, "procurement"),
      icon: <CartIcon size={19} />,
    },
    { to: "/approvals", text: "Approvals", show: true, icon: <ShieldIcon size={19} /> },
    { to: "/activity", text: "Command Center", show: true, icon: <BoltIcon size={19} /> },
    {
      to: "/users",
      text: "Users",
      show: user.role === "admin",
      icon: <UsersIcon size={19} />,
    },
  ].filter((l) => l.show);
  // The top row keeps the cross-department pages one click away; the rail holds every page.
  const topTabs = links.filter((l) => ["/dashboard", "/approvals", "/activity"].includes(l.to));
  const closeMenu = () => setMenuOpen(false);

  return (
    <TourProvider>
      <div className="min-h-screen">
        <header className="sticky top-0 z-40 bg-navy-950/70 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-[1680px] items-center gap-2 px-4 md:gap-3 md:px-6">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              className="grid h-9 w-9 place-items-center rounded-lg text-slate-300 hover:bg-white/5 md:hidden"
            >
              {menuOpen ? <CloseIcon /> : <MenuIcon />}
            </button>
            <Link to="/" className="flex shrink-0 items-center gap-2" onClick={closeMenu}>
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-navy-900 ring-1 ring-white/[0.07] card-shadow">
                <LogoMark size={24} />
              </span>
              <span className="hidden text-[15px] font-bold text-white sm:inline">
                UNIFY <span className="font-medium text-slate-400">SUITE</span>
              </span>
            </Link>
            <nav aria-label="Shortcuts" className="ml-4 hidden items-center gap-1 lg:flex">
              {topTabs.map((l) => (
                <NavLink key={l.to} to={l.to} className={pill}>
                  <span className="opacity-70">{l.icon}</span>
                  {l.text}
                </NavLink>
              ))}
            </nav>
            <div className="flex-1" />
            <div className="hidden w-56 md:block 2xl:w-72">
              <SearchBox />
            </div>
            <ThemeSwitch />
            <TourButton />
            <NotificationBell key={user.id} />
            <UserMenu />
          </div>
          {menuOpen && (
            <div className="anim-rise border-t border-white/5 px-4 pt-3 pb-4 md:hidden">
              <div className="mb-3">
                <SearchBox onNavigate={closeMenu} />
              </div>
              <nav aria-label="Main" className="grid grid-cols-2 gap-1">
                {links.map((l) => (
                  <NavLink key={l.to} to={l.to} className={pill} onClick={closeMenu}>
                    {l.icon}
                    {l.text}
                  </NavLink>
                ))}
              </nav>
            </div>
          )}
        </header>
        <div className="mx-auto flex max-w-[1680px] gap-6 md:pr-6">
          <SideRail links={links} />
          {/* Keyed by user: after a demo role switch every page reloads its data as the new user. */}
          <main key={user.id} className="min-w-0 flex-1 px-4 py-6 md:px-0">
            {/* A new page settles in (keyed by path, so polling never replays it). */}
            <div key={pathname} className="anim-page">
              <Outlet />
            </div>
          </main>
        </div>
        <TourInvite />
      </div>
      {!leader && <AuraDock />}
    </TourProvider>
  );
}
