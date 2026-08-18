import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Coins, Radar, ShieldCheck, Zap } from "lucide-react";

const HERO = "/images/snorlax.jpg";
const PSYDUCK = "/images/psyduck.jpg";

const ADVANTAGES = [
  {
    icon: Radar,
    title: "Veterans of the Scene:",
    body: "Dominating the gray market since 2018. We established the standard that everyone else tries to copy.",
  },
  {
    icon: Coins,
    title: "Wholesale Pricing:",
    body: "We completely bypass retail markups to bring you bottomless coins and weekly event tickets at a fraction of the cost.",
  },
  {
    icon: Zap,
    title: "Rapid, Human Fulfillment:",
    body: "No waiting for days. Our dedicated human operators are on standby 24/7 to securely log in, deliver your resources, and instantly log out.",
  },
  {
    icon: ShieldCheck,
    title: "Elite Shundo Hunting:",
    body: "Targeted, specialized shiny-hundo acquisition powered by proprietary routing tools you won't find anywhere else.",
  },
];

export default function About() {
  return (
    <div data-testid="about-page">
      <section className="scanlines relative overflow-hidden border-b border-[#1f1f1f]">
        <img src={HERO} alt="" className="absolute inset-0 h-full w-full object-cover opacity-25" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#050505] via-[#050505]/90 to-transparent" />
        <div className="relative mx-auto max-w-[1400px] px-5 py-20 lg:px-10 lg:py-28">
          <motion.div initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6 }}>
            <p className="text-xs font-bold uppercase tracking-[0.35em] text-[#00ffcc]">// dossier</p>
            <h1 className="mt-6 font-display text-4xl font-black leading-none tracking-tighter sm:text-5xl lg:text-6xl">
              About PokeCoins
            </h1>
            <h2 className="mt-6 font-display text-base text-[#00ffcc] md:text-lg">
              The Industry Standard Since 2018
            </h2>
          </motion.div>
        </div>
      </section>

      <section className="mx-auto grid max-w-[1400px] gap-14 px-5 py-20 lg:grid-cols-12 lg:px-10 lg:py-28">
        <div className="space-y-6 lg:col-span-7">
          <p className="text-sm leading-relaxed text-zinc-300">
            Founded in 2018, PokeCoins was built by a specialized syndicate of underground trainers and
            security experts who saw a massive flaw in the mobile gaming industry: players were being
            drastically overcharged for basic in-game resources. We stepped in to rewrite the rules.
          </p>
          <p className="text-sm leading-relaxed text-zinc-300">
            For over half a decade, we have been the undisputed market leaders in digital game asset
            logistics. From high-volume PokéCoin drops to elite, targeted Shundo acquisition, our team of
            dedicated operators has safely and successfully processed hundreds of thousands of orders for
            trainers globally.
          </p>
        </div>
        <div className="lg:col-span-5">
          <div className="border border-[#1f1f1f] bg-[#0a0a0a] p-6">
            <p className="font-display text-5xl text-[#00ffcc] neon-text">2018</p>
            <p className="mt-3 text-[10px] uppercase tracking-[0.25em] text-zinc-500">
              Operating since · hundreds of thousands of orders
            </p>
          </div>
        </div>
      </section>

      <section className="border-y border-[#1f1f1f] bg-[#070707]">
        <div className="mx-auto grid max-w-[1400px] gap-12 px-5 py-20 lg:grid-cols-12 lg:px-10 lg:py-28">
          <div className="lg:col-span-7">
            <h2 className="font-display text-base text-white md:text-lg">
              The Foremost Experts in Account Safety
            </h2>
            <p className="mt-6 text-sm leading-relaxed text-zinc-300">
              We aren't just digital marketplace vendors; we are security specialists. While amateur providers
              rely on risky, detectable botnets that get accounts instantly flagged, our proprietary,
              end-to-end encrypted routing ensures your PTC credentials are handled with absolute precision.
              Our operators utilize private, undetected location-simulation frameworks, allowing us to maintain
              a flawless, ban-free track record since our inception. We understand the algorithms, we know the
              limits, and we keep your account invisible to the radar.
            </p>
          </div>
          <div className="lg:col-span-5">
            <img src={PSYDUCK} alt="" className="w-full border border-[#9966cc]/40 object-cover" />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1400px] px-5 py-20 lg:px-10 lg:py-28">
        <h2 className="font-display text-base text-white md:text-lg">The PokeCoins Advantage</h2>
        <div className="mt-12 grid gap-8 sm:grid-cols-2">
          {ADVANTAGES.map((a) => (
            <motion.div
              key={a.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45 }}
              className="border border-[#1f1f1f] bg-[#0a0a0a] p-6"
            >
              <a.icon className="h-5 w-5 text-[#00ffcc]" />
              <p className="mt-4 text-sm leading-relaxed text-zinc-300">
                <strong className="font-display text-white">{a.title}</strong> {a.body}
              </p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="border-t border-[#1f1f1f] bg-[#070707]">
        <div className="mx-auto max-w-[1400px] px-5 py-20 lg:px-10 lg:py-28">
          <h2 className="font-display text-base text-white md:text-lg">Our Mission</h2>
          <p className="mt-6 max-w-3xl text-sm leading-relaxed text-zinc-300">
            To keep your inventory locked and loaded without draining your wallet, while providing the most
            secure, anonymous delivery on the market.
          </p>
          <p className="mt-6 font-display text-lg text-[#00ffcc] neon-text">
            Welcome to the premier underground trainer supply.
          </p>
          <Link
            to="/products"
            data-testid="about-shop-btn"
            className="mt-10 inline-block border border-[#00ffcc] px-8 py-4 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
          >
            Browse Products
          </Link>
        </div>
      </section>
    </div>
  );
}
