import { STATUS_LABELS } from "@/lib/api";

const STYLES = {
  awaiting_payment: "border-zinc-700 text-zinc-400",
  pending: "border-[#f4d03f] text-[#f4d03f]",
  processing: "border-[#9966cc] text-[#9966cc]",
  completed: "border-[#00ffcc] text-[#00ffcc]",
  cancelled: "border-[#ff3b30] text-[#ff3b30]",
};

export const StatusBadge = ({ status, testId }) => (
  <span
    data-testid={testId || `status-${status}`}
    className={`border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] ${STYLES[status] || STYLES.pending}`}
  >
    {STATUS_LABELS[status] || status}
  </span>
);
