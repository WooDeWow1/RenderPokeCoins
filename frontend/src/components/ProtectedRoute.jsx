import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export const ProtectedRoute = ({ children, adminOnly = false }) => {
  const { user } = useAuth();
  if (user === null)
    return (
      <div className="flex h-[60vh] items-center justify-center text-xs uppercase tracking-[0.3em] text-zinc-500">
        Authenticating…
      </div>
    );
  if (user === false) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
};
