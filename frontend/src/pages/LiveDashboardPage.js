import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { TrendingUp, TrendingDown, ShoppingBag, DollarSign, Clock, Award, Sparkles, Zap } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const LOGO_URL = '/assets/ganoh-logo.png';

const formatBRL = (v) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0);

const PAYMENT_LABEL = { pix: 'PIX', cash: 'Dinheiro', debit: 'Débito', credit: 'Crédito', voucher: 'Voucher', prazo: 'Fiado' };
const PAYMENT_COLOR = { pix: '#22c55e', cash: '#facc15', debit: '#3b82f6', credit: '#a855f7', voucher: '#06b6d4', prazo: '#f97316' };

/**
 * Counter that animates from previous to new value
 */
const AnimatedNumber = ({ value, format = (v) => v, duration = 800 }) => {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);

  useEffect(() => {
    const start = prevRef.current;
    const end = value;
    const startTime = performance.now();
    let raf;

    const tick = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * eased;
      setDisplay(current);
      if (progress < 1) raf = requestAnimationFrame(tick);
      else prevRef.current = end;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <span>{format(display)}</span>;
};

const KpiCard = ({ icon: Icon, label, value, accent, delay = 0, sub }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.6, delay }}
    className="relative overflow-hidden rounded-2xl p-6 backdrop-blur-xl"
    style={{
      background: `linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))`,
      boxShadow: `0 0 0 1px rgba(255,255,255,0.06), 0 20px 60px -20px ${accent}33`,
    }}
    data-testid={`kpi-${label.replace(/\s/g, '-').toLowerCase()}`}
  >
    <div className="absolute -top-12 -right-12 h-32 w-32 rounded-full opacity-20 blur-2xl"
         style={{ background: accent }} />
    <div className="relative flex items-start justify-between">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-white/40">{label}</p>
        <p className="mt-3 text-4xl font-light text-white" style={{ fontFamily: 'Cormorant Garamond, serif', letterSpacing: '-0.02em' }}>
          {value}
        </p>
        {sub && <p className="mt-2 text-xs text-white/30">{sub}</p>}
      </div>
      <div className="h-10 w-10 rounded-full flex items-center justify-center"
           style={{ background: `${accent}1a`, color: accent }}>
        <Icon className="h-5 w-5" />
      </div>
    </div>
  </motion.div>
);

const HourlyChart = ({ data }) => {
  const max = Math.max(...data.map(d => d.total), 1);
  const currentHour = new Date().getHours();

  return (
    <div className="rounded-2xl p-6 backdrop-blur-xl"
         style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
                  boxShadow: '0 0 0 1px rgba(255,255,255,0.06)' }}>
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-white/40">Vendas por Hora</p>
          <h3 className="text-2xl font-light text-white mt-1" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
            Fluxo do <span className="italic text-[#a8d96b]">dia</span>
          </h3>
        </div>
        <Sparkles className="h-4 w-4 text-[#a8d96b]/60" />
      </div>
      <div className="flex items-end gap-1.5 h-44" data-testid="hourly-chart">
        {data.map((d, i) => {
          const h = (d.total / max) * 100;
          const isCurrent = d.hour === currentHour;
          const isPast = d.hour < currentHour;
          return (
            <div key={d.hour} className="flex-1 flex flex-col items-center gap-2 group">
              <span className="text-[10px] text-white/40 opacity-0 group-hover:opacity-100 transition-opacity">
                {formatBRL(d.total)}
              </span>
              <motion.div
                initial={{ height: 0 }}
                animate={{ height: `${h}%` }}
                transition={{ duration: 1, delay: i * 0.04, ease: [0.34, 1.56, 0.64, 1] }}
                className="w-full rounded-t-lg relative"
                style={{
                  background: isCurrent
                    ? 'linear-gradient(180deg, #a8d96b, rgba(168,217,107,0.3))'
                    : isPast
                      ? 'linear-gradient(180deg, rgba(168,217,107,0.5), rgba(168,217,107,0.1))'
                      : 'rgba(255,255,255,0.04)',
                  boxShadow: isCurrent ? '0 0 24px rgba(168,217,107,0.6)' : 'none',
                  minHeight: h > 0 ? '4px' : '0',
                }}
              >
                {isCurrent && (
                  <motion.div
                    className="absolute -top-1 left-1/2 -translate-x-1/2 h-2 w-2 rounded-full bg-[#a8d96b]"
                    animate={{ scale: [1, 1.6, 1], opacity: [1, 0.4, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                )}
              </motion.div>
              <span className={`text-[10px] tabular-nums ${isCurrent ? 'text-[#a8d96b] font-semibold' : 'text-white/30'}`}>
                {d.hour}h
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const TopItems = ({ items }) => (
  <div className="rounded-2xl p-6 backdrop-blur-xl h-full"
       style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
                boxShadow: '0 0 0 1px rgba(255,255,255,0.06)' }}>
    <div className="flex items-center justify-between mb-5">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-white/40">Mais Vendidos</p>
        <h3 className="text-2xl font-light text-white mt-1" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
          Top <span className="italic text-[#a8d96b]">do dia</span>
        </h3>
      </div>
      <Award className="h-4 w-4 text-[#a8d96b]/60" />
    </div>
    <div className="space-y-3" data-testid="top-items">
      <AnimatePresence>
        {items.length === 0 && (
          <p className="text-sm text-white/30 py-8 text-center">Aguardando primeiros pedidos…</p>
        )}
        {items.map((it, i) => (
          <motion.div
            key={it.name}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: i * 0.08 }}
            className="flex items-center gap-3"
          >
            <div className="h-7 w-7 rounded-full flex items-center justify-center text-xs font-medium"
                 style={{
                   background: i === 0 ? 'linear-gradient(135deg, #fde68a, #f59e0b)' : i === 1 ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)',
                   color: i === 0 ? '#451a03' : i === 1 ? '#fff' : '#9ca3af',
                 }}>
              {i + 1}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white/85 truncate">{it.name}</p>
              <div className="mt-1 h-0.5 bg-white/[0.04] rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${(it.qty / (items[0]?.qty || 1)) * 100}%` }}
                  transition={{ duration: 0.8, delay: 0.2 + i * 0.08 }}
                  className="h-full bg-gradient-to-r from-[#a8d96b] to-[#6ba33b]"
                />
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm text-white font-medium tabular-nums">{it.qty}x</p>
              <p className="text-[10px] text-white/40">{formatBRL(it.revenue)}</p>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  </div>
);

const PaymentBreakdown = ({ data }) => {
  const total = Object.values(data).reduce((s, v) => s + v, 0);
  const entries = Object.entries(data).filter(([k]) => k !== 'prazo' && data[k] > 0);

  return (
    <div className="rounded-2xl p-6 backdrop-blur-xl"
         style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
                  boxShadow: '0 0 0 1px rgba(255,255,255,0.06)' }}>
      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-white/40">Métodos de Pagamento</p>
          <h3 className="text-2xl font-light text-white mt-1" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
            Receita por <span className="italic text-[#a8d96b]">método</span>
          </h3>
        </div>
      </div>
      {entries.length === 0 && (
        <p className="text-sm text-white/30 py-8 text-center">Nenhum pagamento hoje</p>
      )}
      <div className="space-y-3" data-testid="payment-breakdown">
        {entries.map(([k, v]) => {
          const pct = (v / total) * 100;
          return (
            <div key={k}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-white/60">{PAYMENT_LABEL[k] || k}</span>
                <span className="text-xs text-white font-medium tabular-nums">{formatBRL(v)}</span>
              </div>
              <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 1, ease: 'easeOut' }}
                  className="h-full rounded-full"
                  style={{ background: PAYMENT_COLOR[k] || '#a8d96b' }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ActivityFeed = ({ activity }) => (
  <div className="rounded-2xl p-6 backdrop-blur-xl"
       style={{ background: 'linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))',
                boxShadow: '0 0 0 1px rgba(255,255,255,0.06)' }}>
    <div className="flex items-center justify-between mb-5">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-white/40">Atividade</p>
        <h3 className="text-2xl font-light text-white mt-1" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
          Pedidos <span className="italic text-[#a8d96b]">recentes</span>
        </h3>
      </div>
      <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 1.8, repeat: Infinity }}>
        <div className="h-2 w-2 rounded-full bg-[#a8d96b]" style={{ boxShadow: '0 0 10px #a8d96b' }} />
      </motion.div>
    </div>
    <div className="space-y-2.5 max-h-72 overflow-hidden" data-testid="activity-feed">
      <AnimatePresence>
        {activity.length === 0 && (
          <p className="text-sm text-white/30 py-8 text-center">Aguardando pedidos…</p>
        )}
        {activity.map((a) => (
          <motion.div
            key={a.id}
            initial={{ opacity: 0, x: -20, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 20 }}
            transition={{ duration: 0.4 }}
            className="flex items-center gap-3 py-2"
          >
            <div className="h-1.5 w-1.5 rounded-full flex-shrink-0"
                 style={{
                   background: a.status === 'delivered' ? '#22c55e'
                             : a.status === 'ready' ? '#a8d96b'
                             : a.status === 'preparing' ? '#facc15' : '#9ca3af',
                 }} />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white/85 truncate">{a.customer}</p>
              <p className="text-[10px] text-white/30">
                {a.items_count} {a.items_count === 1 ? 'item' : 'itens'} · {PAYMENT_LABEL[a.payment_method] || a.payment_method}
              </p>
            </div>
            <p className="text-sm text-white font-medium tabular-nums">{formatBRL(a.total)}</p>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  </div>
);

const LiveDashboardPage = () => {
  const { store } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    let cancelled = false;
    const fetchSnapshot = async () => {
      try {
        const res = await axios.get(`${API}/live/${store}/snapshot`);
        if (!cancelled) {
          setData(res.data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    };
    fetchSnapshot();
    const interval = setInterval(fetchSnapshot, 7000);
    const clockInterval = setInterval(() => setClock(new Date()), 1000);
    return () => {
      cancelled = true;
      clearInterval(interval);
      clearInterval(clockInterval);
    };
  }, [store]);

  if (error && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-white">
        <div className="text-center">
          <p className="text-white/40 text-sm">Erro ao conectar</p>
          <p className="text-white/20 text-xs mt-2">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <motion.div
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.95, 1, 0.95] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <img src={LOGO_URL} alt="GANOH" className="h-16" />
        </motion.div>
      </div>
    );
  }

  const k = data.kpis;
  const positiveGrowth = k.growth_pct >= 0;
  const STORE_LABELS = { 'runner': 'Runner', 'gym-londres': 'GYM Londres' };
  const storeLabel = STORE_LABELS[store] || (store || '').toUpperCase();
  const hasSalesToday = (k.total_today || 0) > 0;

  return (
    <div
      className="min-h-screen text-white relative overflow-hidden"
      style={{ background: 'radial-gradient(ellipse at top, #0d1a0d 0%, #050505 60%, #000 100%)' }}
      data-testid="live-dashboard"
    >
      {/* Grain texture */}
      <div className="absolute inset-0 opacity-[0.04] pointer-events-none"
           style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.9\' numOctaves=\'3\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")' }} />

      {/* Ambient light spots */}
      <motion.div
        className="absolute top-0 left-1/4 h-96 w-96 rounded-full pointer-events-none"
        style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.15), transparent 60%)', filter: 'blur(60px)' }}
        animate={{ x: [0, 60, 0], y: [0, 40, 0] }}
        transition={{ duration: 20, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute bottom-0 right-1/4 h-96 w-96 rounded-full pointer-events-none"
        style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.08), transparent 60%)', filter: 'blur(60px)' }}
        animate={{ x: [0, -60, 0], y: [0, -40, 0] }}
        transition={{ duration: 25, repeat: Infinity, ease: 'easeInOut' }}
      />

      <div className="relative max-w-[1800px] mx-auto px-8 py-6">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="flex items-center justify-between mb-8"
        >
          <div className="flex items-center gap-5">
            <img src={LOGO_URL} alt="GANOH" className="h-12" />
            <div>
              <p className="text-[10px] uppercase tracking-[0.3em] text-[#a8d96b]/70">Live · {storeLabel}</p>
              <h1 className="text-2xl font-light text-white" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
                Painel <span className="italic text-[#a8d96b]">ao Vivo</span>
              </h1>
            </div>
          </div>
          <div className="text-right">
            <p className="text-3xl font-light tabular-nums text-white" style={{ fontFamily: 'Cormorant Garamond, serif' }}>
              {clock.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
            </p>
            <p className="text-xs text-white/40 capitalize">
              {clock.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
          </div>
        </motion.header>

        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <KpiCard
            icon={DollarSign}
            label="Faturamento Hoje"
            value={<AnimatedNumber value={k.total_today} format={formatBRL} />}
            accent="#a8d96b"
            delay={0.1}
            sub={`Ontem: ${formatBRL(k.total_yesterday)}`}
          />
          <KpiCard
            icon={ShoppingBag}
            label="Pedidos"
            value={<AnimatedNumber value={k.orders_today} format={(v) => Math.round(v)} />}
            accent="#3b82f6"
            delay={0.2}
            sub={`${k.pending_orders} em preparo · ${k.ready_orders} prontos`}
          />
          <KpiCard
            icon={Zap}
            label="Ticket Médio"
            value={<AnimatedNumber value={k.avg_ticket} format={formatBRL} />}
            accent="#facc15"
            delay={0.3}
          />
          <KpiCard
            icon={hasSalesToday && positiveGrowth ? TrendingUp : TrendingDown}
            label="vs. Ontem"
            value={hasSalesToday ? `${positiveGrowth ? '+' : ''}${k.growth_pct.toFixed(1)}%` : '—'}
            accent={hasSalesToday ? (positiveGrowth ? '#22c55e' : '#ef4444') : '#9ca3af'}
            delay={0.4}
            sub={hasSalesToday ? (positiveGrowth ? 'Crescimento' : 'Em queda') : 'Sem vendas hoje ainda'}
          />
        </div>

        {/* Charts grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
          <div className="lg:col-span-2">
            <HourlyChart data={data.hourly_chart} />
          </div>
          <TopItems items={data.top_items} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PaymentBreakdown data={data.by_payment} />
          <ActivityFeed activity={data.activity} />
        </div>

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className="mt-8 flex items-center justify-between text-[10px] text-white/20"
        >
          <p>GANOH CAFÉ · BISTRÔ · {storeLabel}</p>
          <p className="flex items-center gap-2">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#a8d96b] animate-pulse" />
            ATUALIZADO {new Date(data.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </p>
        </motion.div>
      </div>
    </div>
  );
};

export default LiveDashboardPage;
