import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";

export default function Dashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);

  useEffect(() => {
    api.get("/orders").then(({ data }) => setOrders(data)).catch(() => {});
  }, []);

  const active = orders.filter((o) => ["pending", "processing", "awaiting_payment"].includes(o.status));
  const past = orders.filter((o) => ["completed", "cancelled"].includes(o.status));

  const Row = ({ o }) => (
    <Link
      to={`/orders/${o.id}`}
      data-testid={`order-row-${o.id}`}
      className="flex flex-col gap-3 border border-[#1f1f1f] bg-[#0a0a0a] p-5 transition-colors hover:border-[#00ffcc] sm:flex-row sm:items-center sm:justify-between"
    >
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">#{o.id.slice(-8)}</p>
        <p className="mt-2 text-xs text-zinc-200">
          {o.items.map((i) => `${i.name} ×${i.quantity}`).join(" · ")}
        </p>
      </div>
      <div className="flex items-center gap-5">
        <span className="font-display text-sm text-[#00ffcc]">{money(o.total)}</span>
        <StatusBadge status={o.status} testId={`order-status-${o.id}`} />
      </div>
    </Link>
  );

  return (
    <div data-testid="dashboard-page" className="mx-auto max-w-[1200px] px-5 py-16 lg:px-10 lg:py-24">
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// trainer console</p>
      <h1 className="mt-4 font-display text-3xl tracking-tighter">{user?.name}</h1>

      <section className="mt-14">
        <h2 className="mb-6 text-[10px] uppercase tracking-[0.3em] text-zinc-500">Active orders</h2>
        <div className="space-y-4">
          {active.length === 0 && <p data-testid="no-active-orders" className="text-xs text-zinc-600">No active orders.</p>}
          {active.map((o) => <Row key={o.id} o={o} />)}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="mb-6 text-[10px] uppercase tracking-[0.3em] text-zinc-500">History</h2>
        <div className="space-y-4">
          {past.length === 0 && <p className="text-xs text-zinc-600">Nothing archived yet.</p>}
          {past.map((o) => <Row key={o.id} o={o} />)}
        </div>
      </section>
    </div>
  );
}
