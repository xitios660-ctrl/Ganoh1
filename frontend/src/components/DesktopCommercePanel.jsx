import React, { useCallback, useEffect, useRef, useState } from 'react';
import {useDesktopActor} from './DesktopAuthBoundary';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { parseDesktopCents } from '../utils/desktopMoney';
const money = value => ((value || 0) / 100).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const labels = {'cash.deposit': 'Suprimento de caixa', 'cash.withdraw': 'Retirada de caixa', 'expense.create': 'Despesa em dinheiro', 'customer.create': 'Cadastrar cliente', 'prazo.receive': 'Receber dívida em dinheiro','customer.limit':'Definir limite a prazo'};

export default function DesktopCommercePanel({request, onChange}) {
  const actor=useDesktopActor();
  const [data, setData] = useState({customers: [], events: []});
  const [kind, setKind] = useState('expense.create');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [name, setName] = useState('');
  const [reference, setReference] = useState('');
  const [customer, setCustomer] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const retry = useRef(null);
  const refresh = useCallback(async () => {
    try { const value = await request('commerce'); setData({...value, customers: value.customers || [], events: value.events || []}); }
    catch (e) { setError(e.message); }
  }, [request]);
  useEffect(() => { refresh(); const timer = setInterval(refresh, 5000); return () => clearInterval(timer); }, [refresh]);
  async function save(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      if (!retry.current) {
        const selectedCustomer=data.customers.find(c=>c.customer_id===customer);
        if(kind==='customer.limit'&&!selectedCustomer)throw new Error('Selecione o cliente para definir o limite.');
        const fields = kind === 'customer.create' ? {customer_id: crypto.randomUUID(), name} : kind==='customer.limit' ? {customer_id:customer,limit_cents:parseDesktopCents(amount,{allowZero:true}),base_version:selectedCustomer.version,description} : {amount_cents: parseDesktopCents(amount), description};
        if (kind === 'prazo.receive') Object.assign(fields, {customer_id: customer, payment_method: 'cash', payment_reference: reference});
        retry.current = {operation_id: crypto.randomUUID(), kind, data: {business_id: crypto.randomUUID(), ...fields}};
      }
      await request('commerce', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(retry.current)});
      retry.current = null; setAmount(''); setDescription(''); setName('');
      await refresh(); await onChange();
    } catch (e) { if (e.status >= 400 && e.status < 500 && e.status !== 408) retry.current = null; setError(e.message + ' Se a resposta foi perdida, repetir conserva o mesmo identificador.'); }
    finally { setBusy(false); }
  }
  return <Card><CardHeader><CardTitle>Caixa, despesas e clientes — demonstração</CardTitle></CardHeader><CardContent className="space-y-4">
    <p>Saldo local: {money(data.cash_cents)} • Vendas: {money(data.revenue_cents)} • Despesas: {money(data.expense_cents)}</p>
    <p className="text-sm">Valores provisórios locais, sujeitos à sincronização e à revisão de conflitos. Suprimentos e retiradas não contam como faturamento.</p>
    <form onSubmit={save} className="flex flex-wrap gap-3 items-end">
      <label>Operação<select className="block border rounded p-2 bg-background" value={kind} disabled={busy || !!retry.current} onChange={e => setKind(e.target.value)}>{Object.entries(labels).filter(([key])=>actor?.role!=='cashier'||!['cash.deposit','cash.withdraw','customer.limit'].includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      {kind === 'customer.create' ? <label>Nome do cliente<input className="block border rounded p-2 bg-background" value={name} maxLength={120} required disabled={busy || !!retry.current} onChange={e => setName(e.target.value)} /></label> : <>
        <label>Valor (R$)<input className="block border rounded p-2 bg-background w-28" value={amount} inputMode="decimal" required disabled={busy || !!retry.current} onChange={e => setAmount(e.target.value)} /></label>
        <label>Descrição<input className="block border rounded p-2 bg-background" value={description} minLength={3} maxLength={200} required disabled={busy || !!retry.current} onChange={e => setDescription(e.target.value)} /></label>
      </>}
      {['prazo.receive','customer.limit'].includes(kind) && <label>{kind==='customer.limit'?'Cliente do limite':'Cliente com dívida'}<select className="block border rounded p-2 bg-background" value={customer} required disabled={busy || !!retry.current} onChange={e => setCustomer(e.target.value)}><option value="">Selecione</option>{data.customers.filter(c => kind==='customer.limit'||c.debt_cents > 0).map(c => <option key={c.customer_id} value={c.customer_id}>{c.name} — {money(c.debt_cents)}</option>)}</select></label>}
      {kind === 'prazo.receive' && <label>Número do recibo<input className="block border rounded p-2 bg-background" value={reference} required minLength={3} maxLength={100} disabled={busy || !!retry.current} onChange={e => setReference(e.target.value)} /></label>}
      <Button type="submit" disabled={busy}>{retry.current ? 'Repetir lançamento' : 'Salvar lançamento local'}</Button>
    </form>
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <details><summary>Clientes cadastrados ({data.customers.length})</summary><ul>{data.customers.map(c => <li key={c.customer_id}>{c.name} • Dívida local: {money(c.debt_cents)} • Limite {money(c.credit_limit_cents)} {c.credit_approved?'confirmado':'aguardando confirmação'}</li>)}</ul></details>
    <details><summary>Lançamentos comerciais ({data.events.length})</summary><ul>{data.events.map(e => <li key={e.operation_id}>{labels[e.kind] || e.kind} • {e.state} • {e.payload?.description || e.payload?.name} {e.last_error}</li>)}</ul></details>
    <p className="text-sm">Receber não cria nem aumenta dívida. O limite a prazo precisa ser confirmado pelo servidor antes de permitir vendas offline. PIX/cartão exigem confirmação de pagamento e não são liquidados automaticamente.</p>
  </CardContent></Card>;
}
