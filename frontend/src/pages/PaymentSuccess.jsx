import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useCart } from "@/context/CartContext";

export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [state, setState] = useState("checking");
  const [orderId, setOrderId] = useState(null);
  const { clear } = useCart();
  const cleared = useRef(false);

  useEffect(() => {
    if (!sessionId) {
      setState("error");
      return;
    }
    let attempts = 0;
    let timer;
    const poll = async () => {
      attempts += 1;
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        setOrderId(data.order_id);
        if (data.payment_status === "paid") {
          setState("paid");
          if (!cleared.current) {
            cleared.current = true;
            clear();
          }
          return;
        }
        if (["expired", "failed"].includes(data.payment_status)) {
          setState("failed");
          return;
        }
      } catch {
        setState("error");
        return;
      }
      if (attempts >= 10) {
        setState("timeout");
        return;
      }
      timer = setTimeout(poll, 2000);
    };
    poll();
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return (
    <div data-testid="payment-success-page" className="mx-auto max-w-xl px-5 py-24 text-center">
      {state === "checking" && (
        <>
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-[#00ffcc]" />
          <h1 className="mt-6 font-display text-2xl tracking-tighter">Confirming payment…</h1>
        </>
      )}
      {state === "paid" && (
        <>
          <CheckCircle2 className="mx-auto h-10 w-10 text-[#00ffcc]" />
          <h1 data-testid="payment-paid-heading" className="mt-6 font-display text-2xl tracking-tighter">
            Payment confirmed
          </h1>
          <p className="mt-4 text-xs leading-relaxed text-zinc-400">
            Your order is queued. You'll get an alert the moment an operator logs in — stay logged out then.
          </p>
          <Link
            to={orderId ? `/orders/${orderId}` : "/dashboard"}
            data-testid="view-order-btn"
            className="mt-8 inline-block border border-[#00ffcc] px-8 py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] hover:bg-[#00ffcc] hover:text-black"
          >
            Track order
          </Link>
        </>
      )}
      {["failed", "error", "timeout"].includes(state) && (
        <>
          <XCircle className="mx-auto h-10 w-10 text-[#ff3b30]" />
          <h1 className="mt-6 font-display text-2xl tracking-tighter">
            {state === "timeout" ? "Still processing" : "Payment not completed"}
          </h1>
          <p className="mt-4 text-xs text-zinc-400">
            Check your dashboard in a minute — if it stays unpaid, try checkout again.
          </p>
          <Link to="/dashboard" className="mt-8 inline-block border border-zinc-700 px-8 py-3 text-[11px] uppercase tracking-[0.3em] text-zinc-300 hover:border-white hover:text-white">
            My orders
          </Link>
        </>
      )}
    </div>
  );
}
