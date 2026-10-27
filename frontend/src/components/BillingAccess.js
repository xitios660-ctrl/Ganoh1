import React, { createContext, useContext, useEffect, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';

const BillingContext = createContext({ financials_hidden: true });
let hideMoney = true;
let showKitchenValues = false;
export const financialsHidden = (scope) => hideMoney && !(scope === 'kitchen' && showKitchenValues);
export const useBilling = () => useContext(BillingContext);
const api = `${process.env.REACT_APP_BACKEND_URL || ''}/api/billing/status`;
const message = 'Acesso indisponível por falta de pagamento. Regularize o quanto antes.';

export function BillingAccess({ children }) {
  const location = useLocation();
  const [state, setState] = useState(null);
  const [seconds, setSeconds] = useState(0);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let alive = true;
    let sample = null;
    const update = async () => {
      const started = performance.now();
      try {
        const response = await fetch(api, { cache: 'no-store' });
        if (!response.ok) throw new Error('billing status unavailable');
        const data = await response.json();
        if (!['normal', 'grace', 'suspended'].includes(data.mode)) throw new Error('invalid status');
        if (!alive) return;
        // The server sets the deadline. Refreshing and client clock changes cannot extend it.
        sample = { remaining: Math.max(0, (data.expires_at - data.server_time) * 1000 - (performance.now() - started)),
          monotonic: performance.now(), wall: Date.now(), mode: data.mode };
        hideMoney = data.financials_hidden;
        showKitchenValues = data.kitchen_values_visible === true;
        setSeconds(Math.ceil(sample.remaining / 1000));
        setState(data);
        setUnavailable(false);
      } catch (_) {
        if (alive) setUnavailable(true);
      }
    };
    update();
    const poll = setInterval(update, 15000);
    const tick = setInterval(() => {
      if (!sample || sample.mode !== 'grace') return;
      const elapsed = Math.max(performance.now() - sample.monotonic, Date.now() - sample.wall, 0);
      setSeconds(Math.max(0, Math.ceil((sample.remaining - elapsed) / 1000)));
    }, 250);
    window.addEventListener('online', update);
    window.addEventListener('focus', update);
    return () => { alive = false; clearInterval(poll); clearInterval(tick); window.removeEventListener('online', update); window.removeEventListener('focus', update); };
  }, []);

  const blockedManager = state?.manager_blocked && (/^\/(gestor|auth)(\/|$)/i.test(location.pathname) || /\/live\/?$/i.test(location.pathname));
  const expired = state?.mode === 'suspended' || (state?.mode === 'grace' && seconds <= 0);
  const clock = [Math.floor(seconds / 3600), Math.floor(seconds % 3600 / 60), seconds % 60].map(v => String(v).padStart(2, '0')).join(':');
  const banner = state?.mode === 'grace' && !expired ? (
    <div role="status" data-testid="billing-countdown" style={{ position: 'sticky', top: 0, zIndex: 2147483647, padding: '12px 16px', textAlign: 'center', background: '#fbbf24', color: '#17202e', fontFamily: 'system-ui', lineHeight: 1.5 }}>
      <strong>Uso temporário: <span style={{ fontVariantNumeric: 'tabular-nums' }}>{clock}</span></strong>
      <div style={{ fontSize: 13 }}>Regularize o pagamento o quanto antes. Apenas pedidos e valores da cozinha disponíveis; gestor e caixa bloqueados. Ao zerar, o sistema será suspenso.</div>
    </div>
  ) : null;
  if (!state || unavailable || blockedManager || expired) {
    return <>{banner}<main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#101827', color: '#f8fafc', padding: 24 }}>
      <section style={{ maxWidth: 520, textAlign: 'center', padding: 32, borderRadius: 20, background: '#1e293b' }}>
        <h1 style={{ fontSize: 28, marginBottom: 16 }}>{unavailable ? 'Não foi possível verificar o acesso' : !state ? 'Verificando acesso…' : expired ? 'Sistema temporariamente suspenso' : 'Gestor bloqueado'}</h1>
        <p>{unavailable ? 'Conecte-se à internet e tente novamente.' : state ? message : 'Aguarde um instante.'}</p>
        {blockedManager && !expired && <Link to="/equipe" style={{ color: '#fbbf24', display: 'inline-block', marginTop: 20 }}>Voltar para pedidos e cozinha</Link>}
      </section>
    </main></>;
  }
  return <BillingContext.Provider value={state}>{banner}{children}</BillingContext.Provider>;
}
