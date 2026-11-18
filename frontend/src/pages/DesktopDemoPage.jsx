import React, { useCallback, useEffect, useRef, useState } from 'react';
import DesktopCommercePanel from '../components/DesktopCommercePanel';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';

const money = cents => (cents / 100).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
async function api(path, options) {
  const response = await fetch(`/api/local/${path}`, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const error = new Error(typeof detail.detail === 'string' ? detail.detail : `Serviço local recusou a operação (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}
export default function DesktopDemoPage() {
  const [status, setStatus] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [sales, setSales] = useState([]);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const retry = useRef(null);
  const refresh = useCallback(async () => {
    try {
      const [s, c, orders, events] = await Promise.all([api('status'), api('catalog'), api('sales'), api('sync-history')]);
      setStatus(s); setCatalog(c.items); setSales(orders.items); setHistory(events.items);
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { refresh(); const id = setInterval(refresh, 5000); return () => clearInterval(id); }, [refresh]);
  const product = catalog.find(i => i.sku === selected);
  async function sell(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      if (!retry.current) retry.current = {operation_id: crypto.randomUUID(), sale_id: crypto.randomUUID(), items: [{sku: selected, quantity: Number(quantity)}]};
      await api('sales', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(retry.current)});
      retry.current = null; await refresh();
    } catch (e) { if (e.status >= 400 && e.status < 500 && e.status !== 408) retry.current = null; setError(`${e.message} Repetir usará o mesmo identificador; confira o histórico antes de iniciar outra venda.`); }
    finally { setBusy(false); }
  }
  async function reloadCatalog() {
    setBusy(true);
    try { await api('snapshot/restart', {method: 'POST'}); await api('sync', {method: 'POST'}); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function sync() {
    setBusy(true);
    try { await api('sync', {method: 'POST'}); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-background text-foreground p-6 max-w-5xl mx-auto space-y-6">
    <header><h1 className="text-3xl font-bold text-orange-500">GANOH</h1>
      <p>Demonstração local • {status?.unit === 'runner' ? 'RUNNER' : status?.unit === 'gym-londres' ? 'GYM LONDRES' : 'Carregando unidade'}</p>
      <p className="text-sm">Somente dados fictícios e vendas em dinheiro. Esta demonstração não substitui o atendimento das lojas.</p></header>
    <Card><CardContent className="pt-6 space-y-2" aria-live="polite">
      <p>{status?.connection === 'online' ? 'Servidor de homologação conectado' : 'Offline / servidor indisponível'} • Pendentes: {status?.pending ?? '—'} • Conflitos: {status?.conflicts ?? '—'}</p>
      <p>Última operação sincronizada: {status?.last_synced_at ? new Date(status.last_synced_at).toLocaleString('pt-BR') : 'Nenhuma'}</p>
      <p className="text-sm">Valores locais pendentes ainda não fazem parte dos relatórios remotos.</p>
      {status?.last_error && <p role="status">{status.last_error}</p>}
      <Button variant="outline" onClick={sync} disabled={busy}>Sincronizar agora</Button>
      <Button variant="ghost" onClick={reloadCatalog} disabled={busy}>Reiniciar download do catálogo</Button>
    </CardContent></Card>
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <Card><CardHeader><CardTitle>Registrar venda local</CardTitle></CardHeader><CardContent>
      <form onSubmit={sell} className="flex flex-wrap gap-4 items-end">
        <label>Produto<select className="block border rounded p-2 bg-background" value={selected} disabled={busy || !!retry.current} onChange={e => setSelected(e.target.value)} required>
          <option value="">Selecione</option>{catalog.map(i => <option key={i.sku} value={i.sku}>{i.name || i.sku} — {money(i.price_cents)}</option>)}
        </select></label>
        <label>Quantidade<input className="block border rounded p-2 bg-background w-24" type="number" min="1" max="100" value={quantity} disabled={busy || !!retry.current} onChange={e => setQuantity(e.target.value)} required /></label>
        <p>Total: {money((product?.price_cents || 0) * Number(quantity))}</p>
        <Button type="submit" disabled={busy || !product}>{retry.current ? 'Repetir mesma venda' : 'Salvar venda em dinheiro'}</Button>
      </form>
      {!catalog.length && <p>O catálogo precisa ser carregado na primeira sincronização ou preparado pelo modo de demonstração.</p>}
    </CardContent></Card>
    <DesktopCommercePanel request={api} onChange={refresh} />
    <details><summary>Histórico de sincronização</summary>
      <ul>{history.slice(0, 10).map(e => <li key={e.sequence}>{e.created_at} • {e.connection} {e.message}</li>)}</ul>
    </details>
    <Card><CardHeader><CardTitle>Histórico local</CardTitle></CardHeader><CardContent>
      <ul className="space-y-3">{sales.map(s => <li key={s.operation_id} className="border-b pb-2">
        <p>{money(s.payload.total_cents)} • {s.state === 'pending' ? 'Pendente' : s.state === 'synced' ? 'Sincronizada' : 'Conflito — revisão necessária'}</p>
        <p className="text-xs break-all">{s.operation_id}</p>{s.last_error && <p>{s.last_error}</p>}
      </li>)}</ul>
    </CardContent></Card>
  </main>;
}
