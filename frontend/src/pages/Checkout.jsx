import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, apiError, money } from "@/lib/api";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";

const input =
  "w-full bg-black px-4 py-3 font-mono text-sm text-[#00ffcc] outline-none ring-1 ring-[#00ffcc]/30 transition-shadow focus:ring-[#00ffcc]";
const label = "mb-2 block text-[10px] uppercase tracking-[0.25em] text-zinc-500";

export default function Checkout() {
  const { items, total, invalid } = useCart();
  const { user } = useAuth();
  const isGuest = !user;
  const [email, setEmail] = useState("");
  const [ptcUsername, setPtcUsername] = useState("");
  const [ptcPassword, setPtcPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/orders/checkout", {
        items: items.map((i) => ({ product_id: i.id, quantity: i.quantity })),
        ptc_username: ptcUsername,
        ptc_password: ptcPassword,
        origin_url: window.location.origin,
        ...(isGuest ? { email } : {}),
      });
      if (isGuest) {
        const saved = JSON.parse(localStorage.getItem("pokeforge_guest_orders") || "[]");
        localStorage.setItem(
          "pokeforge_guest_orders",
          JSON.stringify([data.order_id, ...saved.filter((id) => id !== data.order_id)])
        );
      }
      window.location.href = data.checkout_url;
    } catch (err) {
      const msg = apiError(err);
      setError(msg);
      toast.error(msg);
      setBusy(false);
    }
  };

  if (items.length === 0)
    return (
      <div data-testid="checkout-empty" className="mx-auto max-w-2xl px-5 py-24 text-center">
        <h1 className="font-display text-2xl tracking-tighter">Nothing to check out</h1>
        <Link to="/" className="mt-6 inline-block border border-[#00ffcc] px-6 py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] hover:bg-[#00ffcc] hover:text-black">
          Back to store
        </Link>
      </div>
    );

  return (
    <div data-testid="checkout-page" className="mx-auto grid max-w-[1100px] gap-12 px-5 py-16 lg:grid-cols-12 lg:px-10 lg:py-24">
      <div className="lg:col-span-7">
        <h1 className="font-display text-3xl tracking-tighter">Checkout</h1>
        <p className="mt-3 text-xs text-zinc-500">
          We need your Pokémon Trainer Club login to deliver. It is encrypted before it touches the database.
        </p>

        {invalid && (
          <div data-testid="checkout-validation-error" className="mt-8 flex gap-3 border border-[#ff3b30] bg-[#ff3b30]/10 p-4 text-xs text-[#ff3b30]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            An Event Pass requires at least one Pokécoin Bundle in your cart.
          </div>
        )}

        <form onSubmit={submit} className="mt-8 border border-[#00ffcc]/30 bg-black p-6">
          <p className="mb-6 font-mono text-[10px] uppercase tracking-[0.25em] text-[#00ffcc]">
            ~/ptc/secure-handoff $
          </p>
          <div className="space-y-6">
            {isGuest && (
              <div>
                <label className={label}>Email (for order updates)</label>
                <input data-testid="guest-email-input" className={input} type="email" value={email}
                       onChange={(e) => setEmail(e.target.value)} required />
                <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
                  Checking out as a guest.{" "}
                  <Link to="/login" className="text-[#00ffcc] hover:underline">Sign in</Link>{" "}
                  to keep every order in one dashboard.
                </p>
              </div>
            )}
            <div>
              <label className={label}>PTC Username</label>
              <input data-testid="ptc-username-input" className={input} value={ptcUsername}
                     onChange={(e) => setPtcUsername(e.target.value)} autoComplete="off" required />
            </div>
            <div>
              <label className={label}>PTC Password</label>
              <input data-testid="ptc-password-input" className={input} type="password" value={ptcPassword}
                     onChange={(e) => setPtcPassword(e.target.value)} autoComplete="new-password" required />
            </div>
          </div>
          <div className="mt-6 flex gap-3 border border-zinc-800 p-4 text-[11px] leading-relaxed text-zinc-400">
            <ShieldCheck className="h-4 w-4 shrink-0 text-[#00ffcc]" />
            Encrypted at rest with a server-side key. Only a fulfilment operator can decrypt it, and only for
            your order. Change your password after delivery.
          </div>
          {error && (
            <p data-testid="checkout-error" className="mt-6 border border-[#ff3b30] bg-[#ff3b30]/10 p-3 text-xs text-[#ff3b30]">
              {error}
            </p>
          )}
          <button
            data-testid="place-order-btn"
            disabled={busy || invalid}
            className="mt-8 w-full border border-[#00ffcc] py-4 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:cursor-not-allowed disabled:border-zinc-800 disabled:text-zinc-600 disabled:hover:bg-transparent"
          >
            {busy ? "Opening secure payment…" : `Pay ${money(total)} with Stripe`}
          </button>
        </form>
      </div>

      <aside className="lg:col-span-5">
        <div className="border border-[#1f1f1f] bg-[#0a0a0a] p-6">
          <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-500">Order summary</p>
          <div className="mt-5 space-y-4">
            {items.map((i) => (
              <div key={i.id} className="flex justify-between gap-4 text-xs">
                <span className="text-zinc-300">
                  {i.name} <span className="text-zinc-600">× {i.quantity}</span>
                </span>
                <span className="text-white">{money(i.price * i.quantity)}</span>
              </div>
            ))}
          </div>
          <div className="mt-6 flex justify-between border-t border-zinc-800 pt-5 text-xs uppercase tracking-[0.2em] text-zinc-400">
            <span>Total</span>
            <span data-testid="checkout-total" className="font-display text-lg text-[#00ffcc]">{money(total)}</span>
          </div>
          <p className="mt-4 text-[10px] leading-relaxed text-zinc-600">
            Taxes are calculated by Stripe at payment. Test card: 4242 4242 4242 4242.
          </p>
        </div>
      </aside>
    </div>
  );
}
