import React, { useEffect, useState } from 'react';
import { WifiOff, RefreshCw, CheckCircle2 } from 'lucide-react';
import { getOfflineOrders, syncOfflineOrders } from '../services/offlineService';

/**
 * Persistent top banner shown while the device is offline.
 * Also briefly confirms successful sync once connection comes back.
 */
export const OfflineBanner = () => {
  const [isOffline, setIsOffline] = useState(() => !navigator.onLine);
  const [syncing, setSyncing] = useState(false);
  const [justSynced, setJustSynced] = useState(null);
  const [pending, setPending] = useState(() =>
    getOfflineOrders().filter((o) => !o.synced).length
  );

  // Recount pending periodically (so newly saved offline orders show up)
  useEffect(() => {
    const refresh = () => setPending(getOfflineOrders().filter((o) => !o.synced).length);
    const id = setInterval(refresh, 3000);
    window.addEventListener('ganoh:offline-orders-changed', refresh);
    return () => {
      clearInterval(id);
      window.removeEventListener('ganoh:offline-orders-changed', refresh);
    };
  }, []);

  useEffect(() => {
    const handleOffline = () => setIsOffline(true);
    const handleOnline = async () => {
      setIsOffline(false);
      const pendingCount = getOfflineOrders().filter((o) => !o.synced).length;
      if (pendingCount > 0) {
        setSyncing(true);
        try {
          const result = await syncOfflineOrders();
          setJustSynced(result);
          window.dispatchEvent(new Event('ganoh:offline-orders-changed'));
          setTimeout(() => setJustSynced(null), 4000);
        } finally {
          setSyncing(false);
        }
      }
    };
    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
    };
  }, []);

  if (!isOffline && !syncing && !justSynced) return null;

  // Off-line state
  if (isOffline) {
    return (
      <div
        data-testid="offline-banner"
        className="fixed top-0 left-0 right-0 z-[100] bg-amber-500 text-black text-center py-2 px-4 text-sm font-medium shadow-lg flex items-center justify-center gap-2"
      >
        <WifiOff className="h-4 w-4" />
        <span>
          Você está <strong>off-line</strong>. Pedidos serão salvos no aparelho e enviados quando a conexão voltar.
          {pending > 0 && (
            <span className="ml-2 inline-flex items-center gap-1 bg-black/15 px-2 py-0.5 rounded-full text-xs">
              {pending} pedido{pending > 1 ? 's' : ''} pendente{pending > 1 ? 's' : ''}
            </span>
          )}
        </span>
      </div>
    );
  }

  // Syncing
  if (syncing) {
    return (
      <div
        data-testid="offline-banner-syncing"
        className="fixed top-0 left-0 right-0 z-[100] bg-blue-500 text-white text-center py-2 px-4 text-sm font-medium shadow-lg flex items-center justify-center gap-2"
      >
        <RefreshCw className="h-4 w-4 animate-spin" />
        Sincronizando pedidos…
      </div>
    );
  }

  // Just synced
  if (justSynced) {
    return (
      <div
        data-testid="offline-banner-synced"
        className="fixed top-0 left-0 right-0 z-[100] bg-emerald-500 text-white text-center py-2 px-4 text-sm font-medium shadow-lg flex items-center justify-center gap-2"
      >
        <CheckCircle2 className="h-4 w-4" />
        {justSynced.synced > 0
          ? `${justSynced.synced} pedido${justSynced.synced > 1 ? 's' : ''} sincronizado${justSynced.synced > 1 ? 's' : ''}!`
          : 'Conexão restabelecida.'}
        {justSynced.failed > 0 && (
          <span className="ml-2 opacity-90">({justSynced.failed} com erro)</span>
        )}
      </div>
    );
  }

  return null;
};

export default OfflineBanner;
