import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChefHat, Coffee, ArrowLeft, ArrowRight, MapPin, Lock, Package } from 'lucide-react';
import { CinematicBackground } from '../components/CinematicBackground';

const LOGO_URL = '/assets/ganoh-logo.png';

const STORES = [
  { id: 'runner', name: 'Runner' },
  { id: 'gym-londres', name: 'GYM Londres' },
];

const STAFF_PASSWORD = 'ganoh2025';
const STAFF_SESSION_KEY = 'ganoh_staff_unlocked';

/* Tela de acesso interno - separa Cozinha e Gestor em sessões distintas */
export const StaffAccessPage = () => {
  const navigate = useNavigate();
  const [mounted, setMounted] = useState(false);
  // Pre-select last kitchen store opened (localStorage) so user doesn't pick it every day
  const [selectedKitchen, setSelectedKitchen] = useState(() => {
    try {
      const last = localStorage.getItem('ganoh_last_kitchen_store');
      return STORES.some((s) => s.id === last) ? last : null;
    } catch { return null; }
  });
  const [selectedStock, setSelectedStock] = useState(() => {
    try {
      const last = localStorage.getItem('ganoh_last_stock_store');
      return STORES.some((s) => s.id === last) ? last : null;
    } catch { return null; }
  });
  const [unlocked, setUnlocked] = useState(() => {
    try { return sessionStorage.getItem(STAFF_SESSION_KEY) === '1'; } catch { return false; }
  });
  const [pwd, setPwd] = useState('');
  const [pwdError, setPwdError] = useState('');
  const [pwdShake, setPwdShake] = useState(false);

  const handleUnlock = (e) => {
    e.preventDefault();
    if (pwd.trim() === STAFF_PASSWORD) {
      try { sessionStorage.setItem(STAFF_SESSION_KEY, '1'); } catch {}
      setUnlocked(true);
      setPwdError('');
    } else {
      setPwdError('Senha incorreta');
      setPwdShake(true);
      setTimeout(() => setPwdShake(false), 500);
    }
  };

  useEffect(() => { setMounted(true); }, []);

  if (!unlocked) {
    return (
      <div className="ganoh-dark-scene relative min-h-screen bg-[#070707] text-white overflow-hidden">
        <CinematicBackground />
        <button
          onClick={() => navigate('/')}
          className="absolute top-6 left-6 z-20 flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-white/40 hover:text-[#a8d96b] transition font-display"
          data-testid="staff-gate-back-btn"
        >
          <ArrowLeft className="h-3 w-3" /> Voltar
        </button>

        <div className="relative z-10 min-h-screen flex items-center justify-center px-6 py-12">
          <form
            onSubmit={handleUnlock}
            data-testid="staff-password-form"
            className={`relative w-full max-w-sm rounded-3xl border border-[#a8d96b]/25 bg-white/[0.03] backdrop-blur-xl p-8 transition-all duration-1000 ${
              mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
            } ${pwdShake ? 'animate-[shake_0.4s_ease-in-out]' : ''}`}
            style={{
              boxShadow: '0 40px 100px -30px rgba(168,217,107,0.25), inset 0 1px 0 rgba(255,255,255,0.06)',
            }}
          >
            <style>{`@keyframes shake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-8px); } 75% { transform: translateX(8px); } }`}</style>

            <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl pointer-events-none"
              style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.35), transparent 70%)' }} />

            <div className="relative text-center mb-6">
              <div className="relative inline-block mb-4">
                <div className="absolute inset-0 -m-3 rounded-full blur-2xl bg-[#a8d96b]/30" />
                <img
                  src={LOGO_URL}
                  alt="GANOH"
                  className="relative h-12 mx-auto"
                  style={{ filter: 'brightness(1.7) contrast(1.2) saturate(1.1)' }}
                />
              </div>
              <p className="font-display italic text-[10px] uppercase tracking-[0.45em] text-[#a8d96b]/80">
                Área restrita · Equipe
              </p>
              <h1 className="font-heading text-2xl mt-2 font-light tracking-tight">
                Senha de <span className="font-display italic text-[#a8d96b]">acesso</span>
              </h1>
              <div className="mx-auto mt-3 h-px w-10 bg-gradient-to-r from-transparent via-[#a8d96b]/60 to-transparent" />
            </div>

            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-[#a8d96b]/70" />
              <input
                type="password"
                value={pwd}
                onChange={(e) => { setPwd(e.target.value); setPwdError(''); }}
                placeholder="Digite a senha"
                data-testid="staff-password-input"
                autoFocus
                className="w-full pl-11 pr-4 py-3.5 rounded-xl bg-white/[0.04] border border-white/10 focus:border-[#a8d96b]/60 focus:bg-[#a8d96b]/[0.06] outline-none text-sm tracking-[0.2em] text-white placeholder:text-white/30 transition-all"
              />
            </div>

            {pwdError && (
              <p data-testid="staff-password-error" className="mt-3 text-center text-xs text-rose-400/90 tracking-wide">
                {pwdError}
              </p>
            )}

            <button
              type="submit"
              data-testid="staff-password-submit"
              className="mt-5 w-full p-3.5 rounded-xl bg-[#a8d96b] hover:bg-[#bce283] text-black font-medium tracking-wide transition-all flex items-center justify-center gap-2 group"
            >
              Entrar
              <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
            </button>

            <p className="mt-6 text-center font-display italic text-[10px] uppercase tracking-[0.4em] text-white/25">
              Café · Bistrô · <span className="text-[#a8d96b]/50 not-italic">MMXXVI</span>
            </p>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="ganoh-dark-scene relative min-h-screen bg-[#070707] text-white overflow-hidden">
      <CinematicBackground />

      <button
        onClick={() => navigate('/')}
        className="absolute top-6 left-6 z-20 flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-white/40 hover:text-[#a8d96b] transition font-display"
        data-testid="staff-back-btn"
      >
        <ArrowLeft className="h-3 w-3" /> Voltar
      </button>

      <div className="relative z-10 min-h-screen flex flex-col items-center justify-center px-6 py-12">
        <div className="max-w-3xl w-full">
          {/* Header */}
          <div
            className={`text-center mb-12 transition-all duration-1000 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4'}`}
          >
            <div className="relative inline-block mb-4">
              <div className="absolute inset-0 -m-4 rounded-full blur-2xl bg-[#a8d96b]/30" />
              <img
                src={LOGO_URL}
                alt="GANOH"
                className="relative h-14 mx-auto"
                style={{ filter: 'brightness(1.7) contrast(1.2) saturate(1.1)' }}
              />
            </div>
            <p className="font-display italic text-[10px] uppercase tracking-[0.45em] text-[#a8d96b]/80 mt-3">
              Acesso interno
            </p>
            <h1 className="font-heading text-3xl md:text-4xl mt-2 font-light tracking-tight">
              Para quem você <span className="font-display italic text-[#a8d96b]">é?</span>
            </h1>
            <div className="mx-auto mt-4 h-px w-12 bg-gradient-to-r from-transparent via-[#a8d96b]/60 to-transparent" />
          </div>

          {/* SEPARADO: Cozinha | Gestor | Estoque */}
          <div className="grid md:grid-cols-3 gap-5">
            {/* COZINHA - escolhe loja inline */}
            <div
              className={`group relative rounded-2xl border border-white/10 hover:border-[#a8d96b]/40 bg-white/[0.03] hover:bg-white/[0.05] overflow-hidden transition-all duration-500 ${
                mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
              style={{ transitionDelay: '0.15s' }}
              data-testid="staff-kitchen-card"
            >
              {/* corner glow */}
              <div className="absolute -top-12 -right-12 w-44 h-44 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-700"
                style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.3), transparent 70%)' }} />

              <div className="relative p-7">
                <div className="flex items-start justify-between mb-5">
                  <div>
                    <p className="font-display italic text-[10px] uppercase tracking-[0.4em] text-[#a8d96b]/70 mb-2">
                      Equipe operacional
                    </p>
                    <h2 className="font-heading text-2xl font-light tracking-tight">Cozinha</h2>
                    <p className="text-sm text-white/50 mt-1 font-light">
                      Visualizar e preparar os pedidos em tempo real
                    </p>
                  </div>
                  <div
                    className="h-14 w-14 shrink-0 rounded-full flex items-center justify-center"
                    style={{
                      background: 'radial-gradient(circle at 30% 30%, #a8d96b33, #a8d96b08 70%)',
                      border: '1px solid #a8d96b40',
                      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.15)',
                    }}
                  >
                    <ChefHat className="h-6 w-6 text-[#a8d96b]" style={{ filter: 'drop-shadow(0 0 6px #a8d96baa)' }} />
                  </div>
                </div>

                {!selectedKitchen ? (
                  <div className="space-y-2">
                    <p className="text-[10px] uppercase tracking-[0.3em] text-white/40 mb-2">Escolha a unidade</p>
                    {STORES.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setSelectedKitchen(s.id)}
                        data-testid={`staff-kitchen-store-${s.id}`}
                        className="w-full flex items-center justify-between p-3 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/10 hover:border-[#a8d96b]/40 transition-all group/btn"
                      >
                        <span className="flex items-center gap-3">
                          <MapPin className="h-4 w-4 text-[#a8d96b]/80" />
                          <span className="font-heading text-base text-white">{s.name}</span>
                        </span>
                        <ArrowRight className="h-4 w-4 text-white/40 group-hover/btn:text-[#a8d96b] group-hover/btn:translate-x-1 transition-all" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-[10px] uppercase tracking-[0.3em] text-[#a8d96b]/80">
                      Unidade · {STORES.find((s) => s.id === selectedKitchen)?.name}
                    </p>
                    <button
                      onClick={() => {
                        try { localStorage.setItem('ganoh_last_kitchen_store', selectedKitchen); } catch {}
                        navigate(`/${selectedKitchen}/cozinha`);
                      }}
                      data-testid="staff-kitchen-enter"
                      className="w-full p-3.5 rounded-lg bg-[#a8d96b] hover:bg-[#bce283] text-black font-medium tracking-wide transition-all flex items-center justify-center gap-2 group/enter"
                    >
                      Entrar na cozinha
                      <ArrowRight className="h-4 w-4 group-hover/enter:translate-x-1 transition-transform" />
                    </button>
                    <button
                      onClick={() => setSelectedKitchen(null)}
                      className="w-full text-[10px] uppercase tracking-[0.3em] text-white/40 hover:text-white/70 transition py-1"
                    >
                      ← trocar unidade
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* GESTOR - card separado */}
            <div
              className={`group relative rounded-2xl border border-[#a8d96b]/20 hover:border-[#a8d96b]/60 bg-gradient-to-br from-[#a8d96b]/10 via-white/[0.02] to-transparent overflow-hidden transition-all duration-500 ${
                mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
              style={{ transitionDelay: '0.3s' }}
              data-testid="staff-gestor-card"
            >
              {/* corner glow */}
              <div className="absolute -top-12 -right-12 w-44 h-44 rounded-full blur-3xl"
                style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.25), transparent 70%)' }} />

              <div className="relative p-7 flex flex-col h-full">
                <div className="flex items-start justify-between mb-5">
                  <div>
                    <p className="font-display italic text-[10px] uppercase tracking-[0.4em] text-[#a8d96b]/70 mb-2">
                      Administração
                    </p>
                    <h2 className="font-heading text-2xl font-light tracking-tight">Gestor</h2>
                    <p className="text-sm text-white/50 mt-1 font-light">
                      Caixa, gráficos, prazos, WhatsApp, gastos
                    </p>
                  </div>
                  <div
                    className="h-14 w-14 shrink-0 rounded-full flex items-center justify-center"
                    style={{
                      background: 'radial-gradient(circle at 30% 30%, #a8d96b40, #a8d96b10 70%)',
                      border: '1px solid #a8d96b60',
                      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.2), 0 8px 24px #a8d96b22',
                    }}
                  >
                    <Coffee className="h-6 w-6 text-[#a8d96b]" style={{ filter: 'drop-shadow(0 0 6px #a8d96baa)' }} />
                  </div>
                </div>

                <ul className="space-y-1.5 mb-6 text-sm text-white/60 font-light">
                  <li className="flex items-center gap-2"><span className="h-1 w-1 rounded-full bg-[#a8d96b]" /> Painel ao vivo das vendas</li>
                  <li className="flex items-center gap-2"><span className="h-1 w-1 rounded-full bg-[#a8d96b]" /> Controle de caixa Runner + GYM</li>
                  <li className="flex items-center gap-2"><span className="h-1 w-1 rounded-full bg-[#a8d96b]" /> Gestão de fiado e prazos</li>
                </ul>

                <button
                  onClick={() => navigate('/auth')}
                  data-testid="staff-gestor-enter"
                  className="mt-auto w-full p-3.5 rounded-lg bg-[#a8d96b] hover:bg-[#bce283] text-black font-medium tracking-wide transition-all flex items-center justify-center gap-2 group/enter"
                >
                  Acessar painel
                  <ArrowRight className="h-4 w-4 group-hover/enter:translate-x-1 transition-transform" />
                </button>
              </div>
            </div>

            {/* ESTOQUE - escolhe loja inline */}
            <div
              className={`group relative rounded-2xl border border-white/10 hover:border-[#a8d96b]/40 bg-white/[0.03] hover:bg-white/[0.05] overflow-hidden transition-all duration-500 ${
                mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
              style={{ transitionDelay: '0.45s' }}
              data-testid="staff-stock-card"
            >
              <div className="absolute -top-12 -right-12 w-44 h-44 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-700"
                style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.3), transparent 70%)' }} />

              <div className="relative p-7">
                <div className="flex items-start justify-between mb-5">
                  <div>
                    <p className="font-display italic text-[10px] uppercase tracking-[0.4em] text-[#a8d96b]/70 mb-2">
                      Controle de insumos
                    </p>
                    <h2 className="font-heading text-2xl font-light tracking-tight">Estoque</h2>
                    <p className="text-sm text-white/50 mt-1 font-light">
                      Ver e ajustar a quantidade disponível por unidade
                    </p>
                  </div>
                  <div
                    className="h-14 w-14 shrink-0 rounded-full flex items-center justify-center"
                    style={{
                      background: 'radial-gradient(circle at 30% 30%, #a8d96b33, #a8d96b08 70%)',
                      border: '1px solid #a8d96b40',
                      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.15)',
                    }}
                  >
                    <Package className="h-6 w-6 text-[#a8d96b]" style={{ filter: 'drop-shadow(0 0 6px #a8d96baa)' }} />
                  </div>
                </div>

                {!selectedStock ? (
                  <div className="space-y-2">
                    <p className="text-[10px] uppercase tracking-[0.3em] text-white/40 mb-2">Escolha a unidade</p>
                    {STORES.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setSelectedStock(s.id)}
                        data-testid={`staff-stock-store-${s.id}`}
                        className="w-full flex items-center justify-between p-3 rounded-lg bg-white/[0.02] hover:bg-white/[0.06] border border-white/10 hover:border-[#a8d96b]/40 transition-all group/btn"
                      >
                        <span className="flex items-center gap-3">
                          <MapPin className="h-4 w-4 text-[#a8d96b]/80" />
                          <span className="font-heading text-base text-white">{s.name}</span>
                        </span>
                        <ArrowRight className="h-4 w-4 text-white/40 group-hover/btn:text-[#a8d96b] group-hover/btn:translate-x-1 transition-all" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-[10px] uppercase tracking-[0.3em] text-[#a8d96b]/80">
                      Unidade · {STORES.find((s) => s.id === selectedStock)?.name}
                    </p>
                    <button
                      onClick={() => {
                        try { localStorage.setItem('ganoh_last_stock_store', selectedStock); } catch {}
                        navigate(`/${selectedStock}/estoque`);
                      }}
                      data-testid="staff-stock-enter"
                      className="w-full p-3.5 rounded-lg bg-[#a8d96b] hover:bg-[#bce283] text-black font-medium tracking-wide transition-all flex items-center justify-center gap-2 group/enter"
                    >
                      Entrar no estoque
                      <ArrowRight className="h-4 w-4 group-hover/enter:translate-x-1 transition-transform" />
                    </button>
                    <button
                      onClick={() => setSelectedStock(null)}
                      className="w-full text-[10px] uppercase tracking-[0.3em] text-white/40 hover:text-white/70 transition py-1"
                    >
                      ← trocar unidade
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          <p
            className={`text-center font-display italic text-[10px] uppercase tracking-[0.4em] text-white/25 mt-12 transition-opacity duration-1000 ${
              mounted ? 'opacity-100' : 'opacity-0'
            }`}
            style={{ transitionDelay: '0.6s' }}
          >
            Café · Bistrô · <span className="text-[#a8d96b]/50 not-italic">MMXXVI</span>
          </p>
        </div>
      </div>
    </div>
  );
};

export default StaffAccessPage;
