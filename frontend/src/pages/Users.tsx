import { useState, type FormEvent } from "react";
import { api } from "../api";
import { ListIcon, PlusIcon, ShieldIcon, UsersIcon } from "../components/icons";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  ghostButton,
  inputClass,
  primaryButton,
} from "../components/ui";
import { label, when } from "../format";
import { isDemo, useAuth } from "../session";
import { toast } from "../toast";
import type { Department, ManagedUser, Role } from "../types";
import { usePoll } from "../usePoll";

const ROLES: Role[] = ["employee", "manager", "executive", "admin"];
const DEPARTMENTS: Department[] = ["sales", "finance", "hr", "support", "procurement"];
const PASSWORD_HINT = "At least 12 characters, not a common password, without the email name.";

function failure(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong";
}

function NewUser({ onCreated }: { onCreated: () => void }) {
  const empty = { email: "", full_name: "", role: "employee", department: "sales", password: "" };
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof empty) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/users", { method: "POST", body: JSON.stringify(form) });
      toast(`${form.full_name} can now sign in`);
      setForm(empty);
      onCreated();
    } catch (err) {
      setError(failure(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="New user" icon={<PlusIcon size={16} />}>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <input
          className={inputClass}
          placeholder="Full name"
          aria-label="Full name"
          value={form.full_name}
          onChange={set("full_name")}
          required
        />
        <input
          className={inputClass}
          type="email"
          placeholder="Email"
          aria-label="Email"
          autoComplete="off"
          value={form.email}
          onChange={set("email")}
          required
        />
        <input
          className={inputClass}
          type="password"
          placeholder="First password"
          aria-label="First password"
          autoComplete="new-password"
          value={form.password}
          onChange={set("password")}
          required
        />
        <select className={inputClass} aria-label="Role" value={form.role} onChange={set("role")}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {label(r)}
            </option>
          ))}
        </select>
        <select
          className={inputClass}
          aria-label="Department"
          value={form.department}
          onChange={set("department")}
        >
          {DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {label(d)}
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy} className={primaryButton}>
          {busy ? "Adding…" : "Add user"}
        </button>
      </form>
      <p className="mt-3 text-xs text-slate-500">
        {PASSWORD_HINT} Give it to the person yourself; they can change it under Account.
      </p>
      <div className="mt-2">
        <ErrorNote message={error} />
      </div>
    </Card>
  );
}

function UserRow({
  person,
  self,
  onChange,
}: {
  person: ManagedUser;
  self: boolean;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState<string | null>(null);

  const send = async (path: string, init: RequestInit, done: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(path, init);
      toast(done);
      setPassword(null);
      onChange();
    } catch (err) {
      setError(failure(err));
    } finally {
      setBusy(false);
    }
  };
  const patch = (changes: Record<string, unknown>, done: string) =>
    send(`/users/${person.id}`, { method: "PATCH", body: JSON.stringify(changes) }, done);

  const selectClass = "rounded-md border border-navy-800 bg-navy-950 px-2 py-1 text-xs";
  return (
    <>
      <tr className="align-top">
        <td className="py-3 pr-4">
          <div className="text-slate-100">
            {person.full_name} {self && <span className="text-xs text-slate-500">(you)</span>}
          </div>
          <div className="text-xs text-slate-500">{person.email}</div>
        </td>
        <td className="py-3 pr-4">
          <select
            className={selectClass}
            aria-label={`Role of ${person.full_name}`}
            value={person.role}
            disabled={busy || self}
            onChange={(e) => {
              const role = e.target.value;
              if (window.confirm(`Make ${person.full_name} ${label(role)}? They sign in again.`))
                void patch({ role }, `${person.full_name} is now ${label(role)}`);
            }}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
        </td>
        <td className="py-3 pr-4">
          <select
            className={selectClass}
            aria-label={`Department of ${person.full_name}`}
            value={person.department}
            disabled={busy}
            onChange={(e) =>
              void patch(
                { department: e.target.value },
                `${person.full_name} moved to ${label(e.target.value)}`,
              )
            }
          >
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                {label(d)}
              </option>
            ))}
          </select>
        </td>
        <td className="py-3 pr-4">
          <Badge value={person.is_active ? "active" : "disabled"} />
        </td>
        <td className="py-3 pr-4 text-xs whitespace-nowrap text-slate-500">
          {when(person.created_at)}
        </td>
        <td className="py-3 text-right whitespace-nowrap">
          <button
            disabled={busy}
            onClick={() => setPassword(password === null ? "" : null)}
            className={`${ghostButton} mr-2`}
          >
            New password
          </button>
          {!self && (
            <button
              disabled={busy}
              onClick={() => {
                const verb = person.is_active ? "Disable" : "Enable";
                if (window.confirm(`${verb} ${person.full_name}'s account?`))
                  void patch(
                    { is_active: !person.is_active },
                    `${person.full_name} ${person.is_active ? "disabled" : "enabled"}`,
                  );
              }}
              className={ghostButton}
            >
              {person.is_active ? "Disable" : "Enable"}
            </button>
          )}
        </td>
      </tr>
      {(error || password !== null) && (
        <tr>
          <td colSpan={6} className="pb-3">
            <ErrorNote message={error} />
            {password !== null && (
              <form
                className="flex flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send(
                    `/users/${person.id}/password`,
                    { method: "POST", body: JSON.stringify({ password }) },
                    `New password set for ${person.full_name}; their sessions ended`,
                  );
                }}
              >
                <input
                  className={`${inputClass} max-w-72`}
                  type="password"
                  autoComplete="new-password"
                  placeholder={`New password for ${person.full_name}`}
                  aria-label={`New password for ${person.full_name}`}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button type="submit" disabled={busy} className={primaryButton}>
                  Set password
                </button>
                <span className="text-xs text-slate-500">{PASSWORD_HINT}</span>
              </form>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

/** Admins: who can sign in, with which role and department. */
export function Users() {
  const { user } = useAuth();
  const { data, error, reload } = usePoll<ManagedUser[]>("/users");
  return (
    <>
      <PageHeader
        eyebrow="Administration"
        icon={<UsersIcon size={22} />}
        title="Users"
        subtitle="Who can sign in, with which role and department. Every change is in the audit log."
      />
      <div className="space-y-6">
        <NewUser onCreated={() => void reload()} />
        <Card title="Everyone with an account" icon={<ListIcon size={16} />}>
          <ErrorNote message={error} />
          {!data && !error && <Loading rows={4} />}
          {data?.length === 0 && <Empty>No users.</Empty>}
          {data && data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr>
                    <th className="py-2 pr-4">Person</th>
                    <th className="py-2 pr-4">Role</th>
                    <th className="py-2 pr-4">Department</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Added</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-navy-800">
                  {data.map((person) => (
                    <UserRow
                      key={person.id}
                      person={person}
                      self={person.id === user?.id}
                      onChange={() => void reload()}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

/** Everyone: your own account, and changing your password. */
export function Account() {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) return setError("The two new passwords are not the same");
    setBusy(true);
    setError(null);
    try {
      await api("/auth/password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      toast("Password changed. Your other sessions were signed out.");
      setCurrent("");
      setNext("");
      setAgain("");
    } catch (err) {
      setError(failure(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Your account"
        icon={<ShieldIcon size={22} />}
        title={user.full_name}
        subtitle={`${user.email} · ${label(user.role)} · ${label(user.department)}`}
      />
      <Card title="Change password" icon={<ShieldIcon size={16} />}>
        {isDemo(user) ? (
          <p className="text-sm text-slate-400">
            Demo accounts share one password, so it cannot be changed here.
          </p>
        ) : (
          <form onSubmit={submit} className="max-w-sm space-y-3">
            <input
              className={inputClass}
              type="password"
              autoComplete="current-password"
              placeholder="Current password"
              aria-label="Current password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
            <input
              className={inputClass}
              type="password"
              autoComplete="new-password"
              placeholder="New password"
              aria-label="New password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
            <input
              className={inputClass}
              type="password"
              autoComplete="new-password"
              placeholder="New password again"
              aria-label="New password again"
              value={again}
              onChange={(e) => setAgain(e.target.value)}
              required
            />
            <p className="text-xs text-slate-500">{PASSWORD_HINT}</p>
            <ErrorNote message={error} />
            <button type="submit" disabled={busy} className={primaryButton}>
              {busy ? "Saving…" : "Change password"}
            </button>
          </form>
        )}
      </Card>
    </>
  );
}
