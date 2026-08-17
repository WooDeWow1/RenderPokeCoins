import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const input =
  "w-full bg-[#050505] px-4 py-3 text-sm text-white outline-none ring-1 ring-zinc-800 transition-shadow focus:ring-[#00ffcc]";
const label = "mb-2 block text-[10px] uppercase tracking-[0.25em] text-zinc-500";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await register(form.name, form.email, form.password);
      navigate("/dashboard");
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="register-page" className="mx-auto max-w-md px-5 py-20 lg:py-28">
      <h1 className="font-display text-3xl tracking-tighter">Create account</h1>
      <p className="mt-3 text-xs text-zinc-500">One account, every order, one private channel per job.</p>
      <form onSubmit={submit} className="mt-10 space-y-6 border border-[#1f1f1f] bg-[#0a0a0a] p-6">
        <div>
          <label className={label}>Trainer name</label>
          <input data-testid="register-name" className={input} value={form.name} onChange={set("name")} required />
        </div>
        <div>
          <label className={label}>Email</label>
          <input data-testid="register-email" className={input} type="email" value={form.email}
                 onChange={set("email")} required />
        </div>
        <div>
          <label className={label}>Password</label>
          <input data-testid="register-password" className={input} type="password" value={form.password}
                 onChange={set("password")} minLength={6} required />
        </div>
        {error && (
          <p data-testid="register-error" className="border border-[#ff3b30] bg-[#ff3b30]/10 p-3 text-xs text-[#ff3b30]">
            {error}
          </p>
        )}
        <button
          data-testid="register-submit"
          disabled={busy}
          className="w-full border border-[#00ffcc] py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
        >
          {busy ? "Creating…" : "Register"}
        </button>
        <p className="text-xs text-zinc-500">
          Already registered?{" "}
          <Link to="/login" data-testid="go-login" className="text-[#00ffcc] hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
