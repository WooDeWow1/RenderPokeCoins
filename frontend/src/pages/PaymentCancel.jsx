import { Link } from "react-router-dom";
import { XCircle } from "lucide-react";

export default function PaymentCancel() {
  return (
    <div data-testid="payment-cancel-page" className="mx-auto max-w-xl px-5 py-24 text-center">
      <XCircle className="mx-auto h-10 w-10 text-[#f4d03f]" />
      <h1 className="mt-6 font-display text-2xl tracking-tighter">Checkout cancelled</h1>
      <p className="mt-4 text-xs text-zinc-400">Your cart is still intact. Pick up where you left off.</p>
      <Link
        to="/checkout"
        data-testid="retry-checkout-btn"
        className="mt-8 inline-block border border-[#00ffcc] px-8 py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] hover:bg-[#00ffcc] hover:text-black"
      >
        Back to checkout
      </Link>
    </div>
  );
}
