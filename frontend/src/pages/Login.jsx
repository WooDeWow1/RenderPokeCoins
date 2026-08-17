import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const input =
  "w-full bg-[#050505] px-4 py-3 text-sm text-white outline-none ring-1 ring-zinc-800 transition-shadow focus:ring-[#00ffcc]";
const label = "mb-2 block text-[10px] uppercase tracking-[0.25em] text-zinc-500";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await login(email, password);
      navigate(user.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="login-page" className="mx-auto max-w-md px-5 py-20 lg:py-28">
      <h1 className="font-display text-3xl tracking-tighter">Sign in</h1>
      <p className="mt-3 text-xs text-zinc-500">Access your orders and encrypted delivery channel.</p>
      <form onSubmit={submit} className="mt-10 space-y-6 border border-[#1f1f1f] bg-[#0a0a0a] p-6">
        <div>
          <label className={label}>Email</label>
          <input data-testid="login-email" className={input} type="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className={label}>Password</label>
          <input data-testid="login-password" className={input} type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && (
          <p data-testid="login-error" className="border border-[#ff3b30] bg-[#ff3b30]/10 p-3 text-xs text-[#ff3b30]">
            {error}
          </p>
        )}
        <button
          data-testid="login-submit"
          disabled={busy}
          className="w-full border border-[#00ffcc] py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
        >
          {busy ? "Authenticating…" : "Enter"}
        </button>
        <p className="text-xs text-zinc-500">
          No account?{" "}
          <Link to="/register" data-testid="go-register" className="text-[#00ffcc] hover:underline">
            Create one
          </Link>
        </p>
      </form>
    </div>
  );
}
