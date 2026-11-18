import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useDesktopActor} from './DesktopAuthBoundary';
import {Button} from './ui/button';
import {Card, CardContent, CardHeader, CardTitle} from './ui/card';
import {parseDesktopCents} from '../utils/desktopMoney';
const money = value => ((value || 0) / 100).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
export default function DesktopOperationsPanel({request, onChange, revision}) {
  const actor=useDesktopActor();
  const [status, setStatus] = useState({shifts: []});
  const [items, setItems] = useState([]);
  const [cash, setCash] = useState(0);
  const [count, setCount] = useState('0');
  const [sku, setSku] = useState('');
  const [delta, setDelta] = useState('');
  const [reason,setReason]=useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const retry = useRef(null);
  const refresh = useCallback(async () => {
    try {
      const [s,c,f] = await Promise.all([request('status'),request('catalog'),request('commerce')]);
      setStatus({...s, shifts:s.shifts || []}); setItems(c.items || []); setCash(f.cash_cents || 0);
    } catch(e) {setError(e.message);}
  },[request]);
  useEffect(()=>{refresh();},[refresh,revision]);
  useEffect(() => {refresh(); const id=setInterval(refresh,5000); return ()=>clearInterval(id);},[refresh]);
  async function save(kind, data) {
    if(busy) return; setBusy(true); setError('');
    try {
      if(!retry.current) retry.current={operation_id:crypto.randomUUID(),kind,data:{business_id:crypto.randomUUID(),...data}};
      await request('commerce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(retry.current)});
      retry.current=null; await refresh(); await onChange();
    } catch(e) {if(e.status>=400 && e.status<500 && e.status!==408) retry.current=null; setError(e.message);}
    finally {setBusy(false);}
  }
  async function shift(event) {
    event.preventDefault();
    try {
      const counted=parseDesktopCents(count,{allowZero:true});
      if(status.active_shift?.status==='open') await save('cash.close',{shift_id:status.active_shift.shift_id,expected_cents:cash,counted_cents:counted});
      else await save('cash.open',{shift_id:crypto.randomUUID(),counted_cents:counted});
    } catch(e) {setError(e.message);}
  }
  async function reconcile(event){event.preventDefault();try{await save('cash.reconcile',{shift_id:status.active_shift.shift_id,expected_cents:cash,counted_cents:parseDesktopCents(count,{allowZero:true}),description:reason});}catch(e){setError(e.message);}}
  async function adjust(event) {
    event.preventDefault();
    try {
      const item=items.find(i=>i.sku===sku); const amount=Number(delta);
      if(!item || !Number.isSafeInteger(amount) || !amount || Math.abs(amount)>100000) throw new Error('Escolha produto e quantidade inteira de entrada ou saída.');
      await save('stock.adjust',{sku,delta:amount,base_version:item.version,description});
    } catch(e) {setError(e.message);}
  }
  const active=status.active_shift;
  return <Card><CardHeader><CardTitle>Turno de caixa e estoque</CardTitle></CardHeader><CardContent className="space-y-4">
    <p>{active?.status==='open'?'Caixa aberto':active?.status==='needs_review'?'Caixa com diferença — revisão obrigatória':'Caixa fechado'} • Saldo do livro: {money(cash)}</p>
    {active?.status!=='needs_review'&&<form onSubmit={shift} className="flex flex-wrap gap-3 items-end">
      <label>{active?.status==='open'?'Contagem de fechamento':'Contagem de abertura'}<input className="block border rounded p-2 bg-background" value={count} inputMode="decimal" disabled={busy || !!retry.current} onChange={e=>setCount(e.target.value)} required /></label>
      <Button type="submit" disabled={busy || active?.status==='needs_review' || (retry.current && !retry.current.kind.startsWith('cash.'))}>{retry.current?.kind.startsWith('cash.')?'Repetir operação do caixa':active?.status==='open'?'Fechar caixa':'Abrir caixa'}</Button>
    </form>}
    {active?.status==='needs_review'&&(!actor||actor.role==='owner')&&<form onSubmit={reconcile} className="flex flex-wrap gap-3 items-end"><label>Recontagem para conciliação<input className="block border rounded p-2 bg-background" value={count} onChange={e=>setCount(e.target.value)} required disabled={busy||!!retry.current}/></label><label>Motivo da conciliação<input className="block border rounded p-2 bg-background" value={reason} onChange={e=>setReason(e.target.value)} required minLength={10} maxLength={200} disabled={busy||!!retry.current}/></label><Button type="submit" disabled={busy}>Conciliar diferença como proprietário</Button></form>}
    <p className="text-sm">Abrir não cria dinheiro nem receita. Se a contagem final divergir, a diferença fica registrada e o caixa permanece bloqueado para revisão.</p>
    {(!actor||actor.role==='owner')&&<form onSubmit={adjust} className="flex flex-wrap gap-3 items-end">
      <label>Produto do estoque<select className="block border rounded p-2 bg-background" value={sku} required disabled={busy || !!retry.current} onChange={e=>setSku(e.target.value)}><option value="">Selecione</option>{items.map(i=><option key={i.sku} value={i.sku}>{i.name || i.sku} — disponível {i.quantity}{i.blocked?' (em revisão)':''}</option>)}</select></label>
      <label>Quantidade de ajuste<input className="block border rounded p-2 bg-background w-28" type="number" value={delta} required disabled={busy || !!retry.current} onChange={e=>setDelta(e.target.value)} /></label>
      <label>Motivo do ajuste<input className="block border rounded p-2 bg-background" value={description} required minLength={3} maxLength={200} disabled={busy || !!retry.current} onChange={e=>setDescription(e.target.value)} /></label>
      <Button type="submit" disabled={busy || (retry.current && retry.current.kind!=='stock.adjust')}>{retry.current?.kind==='stock.adjust'?'Repetir ajuste':'Registrar ajuste'}</Button>
    </form>}
    <p className="text-sm">Quantidade positiva registra entrada; negativa registra saída. Vendas pendentes já reservam estoque localmente. Divergências centrais exigem revisão.</p>
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <details><summary>Histórico de turnos ({status.shifts.length})</summary><ul>{status.shifts.map(s=><li key={s.shift_id}>{s.shift_id} • {s.status}{s.expected_cents!=null?` • Esperado ${money(s.expected_cents)} / contado ${money(s.counted_cents)}`:''}</li>)}</ul></details>
  </CardContent></Card>;
}
