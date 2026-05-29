import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin, ArrowRight, LockKeyhole } from 'lucide-react';
import { AmbientSound } from '../components/AmbientSound';
import { CinematicBackground } from '../components/CinematicBackground';
import { StoreTransition } from '../components/StoreTransition';
import '../styles/store-transition.css';

const LOGO_URL = '/assets/ganoh-logo.png';

const STORES = [
  { id: 'runner', name: 'GANOH Runner', description: 'Academia Runner', tagline: 'Energia · Performance · Sabor' },
  { id: 'gym-londres', name: 'GANOH GYM Londres', description: 'Academia GYM Londres', tagline: 'Força · Foco · Equilíbrio' },
];

/* INTRO "videozinho" - CSS-only, GPU-friendly, ~5.4s total */
const CinematicIntro = ({ onDone }) => {
  useEffect(() => {
    const t = setTimeout(onDone, 5200); // overlap with shutters closing (shutters take 1.6s starting at 4.8s, so reveal at 5.2s)
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black overflow-hidden">
      {/* expanding spotlight */}
      <div className="absolute inset-0 ganoh-intro-spot" />

      {/* concentric rings */}
      <div className="ganoh-intro-ring" style={{ animationDelay: '0.4s' }} />
      <div className="ganoh-intro-ring" style={{ animationDelay: '1.1s' }} />
      <div className="ganoh-intro-ring" style={{ animationDelay: '1.8s' }} />

      {/* particles streaks */}
      <div className="ganoh-intro-streak" style={{ top: '20%', animationDelay: '0.8s' }} />
      <div className="ganoh-intro-streak" style={{ top: '55%', animationDelay: '1.5s' }} />
      <div className="ganoh-intro-streak" style={{ top: '80%', animationDelay: '2.2s' }} />

      {/* logo reveal */}
      <div className="relative z-10 flex flex-col items-center ganoh-intro-logo">
        <div className="absolute inset-0 -m-16 rounded-full blur-3xl ganoh-intro-halo"
          style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.5), transparent 70%)' }} />
        <img
          src={LOGO_URL}
          alt="GANOH Café Bistrô"
          className="relative h-44 md:h-56"
          style={{ filter: 'brightness(1.7) contrast(1.2) saturate(1.1) drop-shadow(0 0 60px rgba(168,217,107,0.6))' }}
        />
        <p className="font-display italic mt-5 text-[#a8d96b] tracking-[0.5em] text-[10px] uppercase ganoh-intro-tag">
          Café · Bistrô · Experiência
        </p>
      </div>

      {/* shutters */}
      <div className="ganoh-intro-shutter-top" />
      <div className="ganoh-intro-shutter-bottom" />

      <button
        onClick={onDone}
        className="absolute bottom-7 right-7 text-[10px] tracking-[0.4em] text-white/40 hover:text-[#a8d96b] transition uppercase font-display z-20"
        data-testid="skip-intro-btn"
      >
        Pular →
      </button>
    </div>
  );
};

export const StoreSelectorPage = () => {
  const navigate = useNavigate();
  const [introDone, setIntroDone] = useState(false);
  const [transitioningStore, setTransitioningStore] = useState(null);
  const [transitionOrigin, setTransitionOrigin] = useState({ x: '50%', y: '50%' });

  useEffect(() => {
    if (sessionStorage.getItem('ganoh_intro_seen')) {
      setIntroDone(true);
    }
  }, []);

  const finishIntro = () => {
    sessionStorage.setItem('ganoh_intro_seen', '1');
    setIntroDone(true);
  };

  const handleStoreClick = (storeId, e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTransitionOrigin({
      x: `${rect.left + rect.width / 2}px`,
      y: `${rect.top + rect.height / 2}px`,
    });
    setTransitioningStore(storeId);
  };

  const completeTransition = () => {
    if (transitioningStore) {
      navigate(`/${transitioningStore}`);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#070707] text-white">
      <CinematicBackground />

      {!introDone && <CinematicIntro onDone={finishIntro} />}

      {/* Acesso interno corner link */}
      <button
        onClick={() => navigate('/equipe')}
        className="absolute top-6 right-6 z-20 group flex items-center gap-2 px-3 py-2 rounded-full bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-[#a8d96b]/40 transition-all"
        data-testid="staff-access-link"
      >
        <LockKeyhole className="h-3 w-3 text-[#a8d96b]/70" />
        <span className="text-[10px] uppercase tracking-[0.3em] text-white/60 group-hover:text-[#a8d96b] transition-colors font-display">
          Sou da equipe
        </span>
      </button>

      <div
        className={`relative z-10 min-h-screen flex flex-col items-center justify-center px-6 py-12 transition-opacity duration-700 ${
          introDone ? 'opacity-100' : 'opacity-0'
        }`}
      >
        <div className="max-w-xl w-full">
          {/* Hero - CSS animations only */}
          <div className="text-center mb-12">
            <div className="relative inline-block">
              <div className="absolute inset-0 -m-12 rounded-full blur-3xl bg-[#a8d96b]/25 ganoh-pulse" />
              <div className="absolute inset-0 -m-5 rounded-full border border-[#a8d96b]/15 ganoh-spin-slow" />
              <div className="absolute inset-0 -m-2 rounded-full border border-dashed border-[#a8d96b]/10 ganoh-spin-reverse" />
              <img
                src={LOGO_URL}
                alt="GANOH"
                className="relative h-24 md:h-28 mx-auto"
                style={{ filter: 'brightness(1.7) contrast(1.2) saturate(1.1) drop-shadow(0 8px 30px rgba(168,217,107,0.45))' }}
                data-testid="ganoh-logo"
              />
            </div>

            <p className="font-display italic mt-7 text-[#a8d96b]/80 text-[10px] tracking-[0.45em] uppercase">
              Bem-vindo
            </p>

            <h1 className="font-heading text-4xl md:text-5xl mt-3 font-light leading-tight tracking-tight">
              Selecione sua{' '}
              <span className="font-display italic text-[#a8d96b] font-medium">unidade</span>
            </h1>

            <div className="mx-auto mt-5 h-px w-16 bg-gradient-to-r from-transparent via-[#a8d96b]/60 to-transparent" />
          </div>

          {/* Stores - pure CSS hover, GPU friendly */}
          <div className="space-y-5">
            {STORES.map((s, i) => (
              <button
                key={s.id}
                onClick={(e) => handleStoreClick(s.id, e)}
                data-testid={`store-${s.id}`}
                className="group relative w-full overflow-hidden rounded-2xl border border-white/10 hover:border-[#a8d96b]/40 bg-white/[0.03] hover:bg-white/[0.05] transition-all duration-500 text-left will-change-transform hover:-translate-y-0.5 ganoh-card-enter"
                style={{ animationDelay: `${0.3 + i * 0.15}s` }}
              >
                {/* corner accent glow */}
                <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-700"
                  style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.35), transparent 60%)' }} />

                <div className="relative p-6 flex items-center gap-5">
                  <div
                    className="relative h-16 w-16 rounded-full flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform duration-500"
                    style={{
                      background: 'radial-gradient(circle at 30% 30%, #a8d96b33, #a8d96b08 70%)',
                      border: '1px solid #a8d96b40',
                      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.15), 0 8px 24px #a8d96b22',
                    }}
                  >
                    <MapPin className="h-7 w-7 text-[#a8d96b]" style={{ filter: 'drop-shadow(0 0 6px #a8d96baa)' }} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="font-heading text-2xl text-white tracking-tight">{s.name}</p>
                    <p className="font-display italic text-sm text-[#a8d96b]/70 mt-0.5">{s.tagline}</p>
                    <p className="text-[10px] uppercase tracking-[0.3em] text-white/40 mt-1.5">{s.description}</p>
                  </div>

                  <div className="shrink-0 h-10 w-10 rounded-full flex items-center justify-center border border-white/10 group-hover:border-[#a8d96b]/50 group-hover:translate-x-1 transition-all">
                    <ArrowRight className="h-4 w-4 text-white/60 group-hover:text-[#a8d96b] transition-colors" />
                  </div>
                </div>

                {/* shine on hover */}
                <span className="absolute top-0 -left-1/3 h-full w-1/3 opacity-0 group-hover:opacity-100 pointer-events-none ganoh-shine-sweep"
                  style={{ background: 'linear-gradient(120deg, transparent, rgba(168,217,107,0.18), transparent)' }} />
              </button>
            ))}
          </div>

          <p className="text-center font-display italic text-[10px] uppercase tracking-[0.4em] text-white/25 mt-12">
            Café · Bistrô · <span className="text-[#a8d96b]/50 not-italic">MMXXVI</span>
          </p>
        </div>
      </div>
      <AmbientSound />
      {transitioningStore && (
        <StoreTransition
          storeId={transitioningStore}
          origin={transitionOrigin}
          onComplete={completeTransition}
        />
      )}
    </div>
  );
};

export default StoreSelectorPage;
