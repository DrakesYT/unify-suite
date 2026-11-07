import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../api";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  PageHeader,
  dangerButton,
  ghostButton,
  inputClass,
  primaryButton,
  Loading,
} from "../components/ui";
import { EmailPanel } from "../components/EmailPanel";
import { VendorHeatmap } from "../components/VendorHeatmap";
import { ProcurementDashboard } from "./procurement/ProcurementDashboard";
import { money, when } from "../format";
import { canWrite, useAuth } from "../session";
import type {
  Page,
  PurchaseOrder,
  PurchaseRequest,
  Quote,
  Vendor,
  VendorComparison,
} from "../types";
import { usePoll } from "../usePoll";
import { WhyButton } from "../components/WhyDrawer";
import { toast } from "../toast";

const ACT_DONE: Record<string, string> = {
  quote: "Quote saved",
  compare: "Vendors ranked",
  approve: "Request approved",
  reject: "Request rejected",
};

const pct = (value: string) => `${(Number(value) * 100).toFixed(0)}%`;

function NewVendor({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [lead, setLead] = useState("7");
  const [rate, setRate] = useState("95");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/procurement/vendors", {
        method: "POST",
        body: JSON.stringify({
          name,
          lead_time_days: Number(lead),
          on_time_rate: (Number(rate) / 100).toFixed(4),
        }),
      });
      toast(`Vendor saved: ${name}`);
      setName("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the vendor");
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <input
        className={inputClass}
        placeholder="Vendor name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-slate-400">
          Lead time (days)
          <input
            className={inputClass}
            type="number"
            min="0"
            value={lead}
            onChange={(e) => setLead(e.target.value)}
          />
        </label>
        <label className="text-xs text-slate-400">
          On-time deliveries (%)
          <input
            className={inputClass}
            type="number"
            min="0"
            max="100"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
          />
        </label>
      </div>
      <button type="submit" className={`${ghostButton} w-full`}>
        Add vendor
      </button>
      <ErrorNote message={error} />
    </form>
  );
}

function NewRequest({ onCreated }: { onCreated: (r: PurchaseRequest) => void }) {
  const [item, setItem] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [budget, setBudget] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const request = await api<PurchaseRequest>("/procurement/requests", {
        method: "POST",
        body: JSON.stringify({
          item,
          quantity: Number(quantity),
          budget_minor: Math.round(Number(budget || 0) * 100),
          currency: "USD",
        }),
      });
      setItem("");
      setBudget("");
      toast(`Purchase request added: ${request.item}`);
      onCreated(request);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the request");
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <input
        className={inputClass}
        placeholder="What do you need?"
        value={item}
        onChange={(e) => setItem(e.target.value)}
        required
      />
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-slate-400">
          Quantity
          <input
            className={inputClass}
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />
        </label>
        <label className="text-xs text-slate-400">
          Budget (USD)
          <input
            className={inputClass}
            type="number"
            min="0"
            step="0.01"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            required
          />
        </label>
      </div>
      <button type="submit" className={`${primaryButton} w-full`}>
        Create request
      </button>
      <ErrorNote message={error} />
    </form>
  );
}

function Ranking({ comparison }: { comparison: VendorComparison }) {
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-2 pr-3">#</th>
              <th className="py-2 pr-3">Vendor</th>
              <th className="py-2 pr-3">Total</th>
              <th className="py-2 pr-3">Lead</th>
              <th className="py-2 pr-3">On time</th>
              <th className="py-2">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-800">
            {comparison.ranking.map((r) => (
              <tr key={r.vendor_id} className={r.rank === 1 ? "text-white" : "text-slate-300"}>
                <td className="py-2 pr-3 font-semibold">{r.rank}</td>
                <td className="py-2 pr-3">
                  {r.vendor_name}
                  {r.over_budget && (
                    <span className="ml-2 text-xs text-amber-300">over budget</span>
                  )}
                </td>
                <td className="py-2 pr-3 whitespace-nowrap">{money(r.total_minor, r.currency)}</td>
                <td className="py-2 pr-3">{r.lead_time_days} d</td>
                <td className="py-2 pr-3">{pct(r.on_time_rate)}</td>
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 rounded-full bg-navy-800">
                      <div
                        className="h-1.5 rounded-full bg-accent-soft"
                        style={{ width: `${r.score}%` }}
                      />
                    </div>
                    {r.score}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Score = 50% price + 25% lead time + 25% on-time record, each relative to the best offer.
      </p>
      {comparison.reason && (
        <p className="rounded-lg bg-navy-950/70 p-3 text-sm text-slate-200">{comparison.reason}</p>
      )}
      {comparison.reason_error && (
        <p className="text-xs text-amber-300">
          No explanation this time ({comparison.reason_error}).
        </p>
      )}
    </div>
  );
}

function RequestDetail({
  request,
  vendors,
  onChange,
}: {
  request: PurchaseRequest;
  vendors: Vendor[];
  onChange: () => void;
}) {
  const { user } = useAuth();
  const editable = Boolean(user && canWrite(user, "procurement"));
  const isManager = Boolean(user && (user.role === "manager" || user.role === "admin"));
  const quotes = usePoll<Quote[]>(`/procurement/requests/${request.id}/quotes`);
  const [vendorId, setVendorId] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const vendorName = new Map(vendors.map((v) => [v.id, v.name]));

  const act = async (what: string, path: string, body: unknown = {}) => {
    setBusy(what);
    setError(null);
    try {
      const res = await api<{ order?: PurchaseOrder }>(path, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (res.order)
        setNote(
          `${res.order.po_number} created for ${money(res.order.amount_minor, res.order.currency)}`,
        );
      toast(
        res.order
          ? `${res.order.po_number} created; it waits for a manager's approval`
          : (ACT_DONE[what] ?? "Done"),
      );
      if (what === "quote") {
        setPrice("");
        await quotes.reload();
      }
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Purchase request">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">
            {request.quantity} × {request.item}
          </h3>
          <p className="text-xs text-slate-500">
            Budget {money(request.budget_minor, request.currency)} · {when(request.created_at)}
          </p>
        </div>
        <Badge value={request.status} />
      </div>

      <h4 className="mt-5 mb-2 text-xs font-semibold text-slate-400">Quotes</h4>
      {(quotes.data ?? []).length === 0 && <p className="text-sm text-slate-500">No quotes yet.</p>}
      <ul className="space-y-1 text-sm">
        {(quotes.data ?? []).map((q) => (
          <li key={q.id} className="flex justify-between text-slate-300">
            <span>{vendorName.get(q.vendor_id) ?? "Vendor"}</span>
            <span>
              {money(q.unit_price_minor, q.currency)} each ·{" "}
              {money(q.unit_price_minor * request.quantity, q.currency)}
            </span>
          </li>
        ))}
      </ul>
      {editable && request.status !== "ordered" && (
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void act("quote", `/procurement/requests/${request.id}/quotes`, {
              vendor_id: vendorId,
              unit_price_minor: Math.round(Number(price) * 100),
            });
          }}
        >
          <select
            className={`${inputClass} flex-1`}
            value={vendorId}
            onChange={(e) => setVendorId(e.target.value)}
            required
          >
            <option value="">Vendor…</option>
            {vendors.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          <input
            className={`${inputClass} w-36`}
            type="number"
            min="0"
            step="0.01"
            placeholder="Unit price"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            required
          />
          <button type="submit" disabled={!!busy} className={ghostButton}>
            Save quote
          </button>
        </form>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-navy-800 pt-4">
        {editable && (
          <button
            disabled={!!busy || (quotes.data ?? []).length < 2}
            onClick={() =>
              act("compare", "/procurement/compare-vendors", { request_id: request.id })
            }
            className={ghostButton}
          >
            {busy === "compare" ? "Comparing…" : "Compare vendors"}
          </button>
        )}
        {isManager && request.status === "pending" && request.requested_by_id !== user?.id && (
          <>
            <button
              disabled={!!busy}
              onClick={() => act("approve", `/procurement/requests/${request.id}/approve`)}
              className={primaryButton}
            >
              Approve request
            </button>
            <button
              disabled={!!busy}
              onClick={() => act("reject", `/procurement/requests/${request.id}/reject`)}
              className={dangerButton}
            >
              Reject
            </button>
          </>
        )}
        {editable && request.status === "approved" && (
          <button
            disabled={!!busy}
            onClick={() => act("order", `/procurement/requests/${request.id}/order`)}
            className={primaryButton}
          >
            {busy === "order" ? "Creating…" : "Create purchase order"}
          </button>
        )}
      </div>
      <ErrorNote message={error} />
      {note && (
        <p className="mt-2 text-sm text-amber-200">
          {note}. It waits for a procurement manager in the{" "}
          <Link to="/approvals" className="underline">
            Approval Center
          </Link>
          .
        </p>
      )}

      {request.comparison && (
        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h4 className="text-xs font-semibold text-slate-400">
              Vendor ranking · {when(request.comparison.compared_at)}
            </h4>
            <WhyButton path={`purchase-request/${request.id}`} />
          </div>
          <Ranking comparison={request.comparison} />
        </div>
      )}
    </Card>
  );
}

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** One purchase order with its delivery status (computed by code) and, when late, a follow-up. */
function OrderRow({
  order,
  vendor,
  editable,
  onChange,
}: {
  order: PurchaseOrder;
  vendor: string;
  editable: boolean;
  onChange: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tracked = order.status === "approved";
  const late = order.delivery_status === "late";

  const markDelivered = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/procurement/orders/${order.id}/delivered`, { method: "POST" });
      toast(`${order.po_number} marked delivered`);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the order");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li id={`po-${order.po_number}`} className="rounded-lg border border-navy-800 px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-slate-300">
        <span className="font-mono text-xs">{order.po_number}</span>
        <span>{vendor}</span>
        <span>{money(order.amount_minor, order.currency)}</span>
        {tracked ? (
          <span className="flex items-center gap-2 text-xs text-slate-400">
            {order.delivered_on
              ? `delivered ${day(order.delivered_on)}`
              : order.expected_delivery
                ? `due ${day(order.expected_delivery)}`
                : "no date"}
            <Badge value={order.delivery_status} />
            {late && <span className="font-semibold text-red-300">{order.days_late} days</span>}
          </span>
        ) : (
          <Badge value={order.status} />
        )}
      </div>
      {tracked && !order.delivered_on && editable && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => void markDelivered()} className={ghostButton}>
            {busy ? "Saving…" : "Mark delivered"}
          </button>
          {late && (
            <button onClick={() => setOpen(!open)} className={ghostButton}>
              {open ? "Hide follow-up" : "Follow up with supplier"}
            </button>
          )}
        </div>
      )}
      <ErrorNote message={error} />
      {(open || (late && !editable)) && (
        <EmailPanel
          title="Supplier follow-up"
          intro="The Supplier Follow-up Writer drafts a chase quoting the PO, the due date and the days late. Nothing is sent until a procurement manager approves it."
          listPath={`/procurement/orders/${order.id}/emails`}
          emailsPath="/procurement/emails"
          managerLabel="a procurement manager"
          editable={editable}
        />
      )}
    </li>
  );
}

export function Procurement() {
  const { user } = useAuth();
  const editable = Boolean(user && canWrite(user, "procurement"));
  const vendors = usePoll<Page<Vendor>>("/procurement/vendors?limit=200");
  const requests = usePoll<Page<PurchaseRequest>>("/procurement/requests?limit=100");
  const orders = usePoll<Page<PurchaseOrder>>("/procurement/orders?limit=100");
  const [picked, setPicked] = useState<string | null>(null);
  const request = requests.data?.items.find((r) => r.id === picked) ?? requests.data?.items[0];
  const vendorList = vendors.data?.items ?? [];
  const vendorName = new Map(vendorList.map((v) => [v.id, v.name]));

  return (
    <>
      <PageHeader
        title="Procurement"
        subtitle="Vendors are ranked by code on price, lead time and on-time record; every purchase order waits for a manager."
      />
      <ProcurementDashboard
        orders={orders.data?.items ?? []}
        requests={requests.data?.items ?? []}
        vendorNames={vendorName}
      />
      <div className="mb-6">
        <VendorHeatmap requests={requests.data?.items ?? []} orders={orders.data?.items ?? []} />
      </div>
      <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
        <div className="min-w-0 space-y-6">
          {editable && (
            <Card title="New request">
              <NewRequest onCreated={(r) => (setPicked(r.id), void requests.reload())} />
            </Card>
          )}
          <Card title="Requests">
            {!requests.data && !requests.error && <Loading rows={3} />}
            {requests.data?.items.length === 0 && <Empty>No purchase requests yet.</Empty>}
            <ul className="space-y-1">
              {requests.data?.items.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => setPicked(r.id)}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm ${
                      r.id === request?.id
                        ? "bg-accent-purple/20 text-white"
                        : "text-slate-300 hover:bg-navy-800"
                    }`}
                  >
                    <span className="truncate">
                      {r.quantity} × {r.item}
                    </span>
                    <Badge value={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Vendors">
            <ul className="mb-3 space-y-1 text-sm">
              {vendorList.map((v) => (
                <li key={v.id} className="flex justify-between text-slate-300">
                  <span>{v.name}</span>
                  <span className="text-xs text-slate-500">
                    {v.lead_time_days} d · {pct(v.on_time_rate)} on time
                  </span>
                </li>
              ))}
            </ul>
            {editable && <NewVendor onCreated={() => void vendors.reload()} />}
          </Card>
        </div>
        <div className="min-w-0 space-y-6">
          {request ? (
            <RequestDetail
              key={request.id}
              request={request}
              vendors={vendorList}
              onChange={() => (void requests.reload(), void orders.reload())}
            />
          ) : (
            <Card>
              {requests.data ? (
                <Empty hint="Add quotes from two or more vendors and the code ranks them.">
                  Create a purchase request to compare vendors.
                </Empty>
              ) : (
                <Loading rows={4} />
              )}
            </Card>
          )}
          <Card title="Purchase orders">
            {!orders.data && !orders.error && <Loading rows={2} />}
            {orders.data?.items.length === 0 && <Empty>No purchase orders yet.</Empty>}
            <ul className="space-y-2 text-sm">
              {orders.data?.items.map((o) => (
                <OrderRow
                  key={o.id}
                  order={o}
                  vendor={vendorName.get(o.vendor_id) ?? ""}
                  editable={editable}
                  onChange={() => void orders.reload()}
                />
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
