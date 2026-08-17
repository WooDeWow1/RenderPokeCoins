import { Lock, Plus } from "lucide-react";
import { motion } from "framer-motion";
import { money } from "@/lib/api";
import { useCart } from "@/context/CartContext";

export const ProductCard = ({ product, featured = false }) => {
  const { add, hasCoins } = useCart();
  const locked = product.category === "event_pass" && !hasCoins;

  return (
    <motion.article
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
      data-testid={`product-card-${product.id}`}
      className="group relative flex flex-col border border-[#1f1f1f] bg-[#0a0a0a] transition-colors hover:border-[#00ffcc]"
    >
      <div className={`relative overflow-hidden ${featured ? "h-56 sm:h-72" : "h-40"}`}>
        <img
          src={product.image_url}
          alt={product.name}
          className="h-full w-full object-cover opacity-80 transition-transform duration-500 group-hover:scale-105"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a] via-transparent to-transparent" />
        {product.badge && (
          <span className="absolute left-3 top-3 border border-[#00ffcc]/60 bg-black/70 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] text-[#00ffcc]">
            {product.badge}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-5">
        <h3 className="font-display text-base font-bold leading-tight">{product.name}</h3>
        <p className="mt-2 flex-1 text-xs leading-relaxed text-zinc-500">{product.description}</p>
        {locked && (
          <p
            data-testid={`locked-notice-${product.id}`}
            className="mt-4 border border-[#f4d03f]/50 bg-[#f4d03f]/10 p-3 text-[10px] leading-relaxed text-[#f4d03f]"
          >
            Locked — add a Pokécoin Bundle to your cart to unlock this Event Pass.
          </p>
        )}
        <div className="mt-5 flex items-center justify-between gap-3">
          <span data-testid={`product-price-${product.id}`} className="font-display text-xl text-[#00ffcc]">
            {money(product.price)}
          </span>
          <button
            data-testid={`add-to-cart-${product.id}`}
            onClick={() => add(product)}
            disabled={product.coming_soon}
            title={locked ? "Requires a Pokécoin Bundle" : "Add to cart"}
            className="flex items-center gap-2 border border-zinc-700 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc] disabled:cursor-not-allowed disabled:border-zinc-900 disabled:text-zinc-600"
          >
            {product.coming_soon ? "Soon" : locked ? <Lock className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
            {!product.coming_soon && (locked ? "Locked" : "Add")}
          </button>
        </div>
      </div>
    </motion.article>
  );
};
