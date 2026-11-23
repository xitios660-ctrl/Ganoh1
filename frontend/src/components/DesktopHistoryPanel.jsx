import React, {useCallback, useEffect, useState} from 'react';
import {Button} from './ui/button';
import {Card, CardContent, CardHeader, CardTitle} from './ui/card';

const labels={orders:'Vendas',order_history:'Histórico de pedidos',stock:'Estoque',menu:'Cardápio',
  adicionais:'Adicionais',prazo_customers:'Clientes a prazo',prazo_payments:'Pagamentos a prazo',
  prazo_partial_payments:'Pagamentos parciais',prazo_debts:'Dívidas a prazo',
  prazo_payment_reversals:'Estornos de pagamentos',prazo_history:'Histórico de prazo',expenses:'Despesas',
  cash_withdrawals:'Retiradas',cash_credit_topups:'Entradas de caixa',cash_drawer_config:'Configuração de caixa',
  pix_adjustments:'Ajustes PIX',stock_movements:'Movimentações de estoque',daily_sales:'Vendas diárias',
  monthly_sales:'Vendas mensais',low_stock_list:'Estoque baixo',whatsapp_inbound:'Pedidos recebidos'};
export function historyText(value){
  if(value==null)return '';
  if(typeof value!=='object')return String(value);
  for(const key of ['$numberDecimal','$numberDouble','$numberInt','$numberLong','$oid']){
    if(typeof value[key]==='string')return value[key];
  }
  if(typeof value.$date==='string')return value.$date;
  return '';
}
export default function DesktopHistoryPanel({request,onChange=()=>{}}){
  const [info,setInfo]=useState(null),[file,setFile]=useState(null),[phrase,setPhrase]=useState('');
  const [collection,setCollection]=useState('orders'),[page,setPage]=useState(null);
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>setInfo(await request('history')),[request]);
  useEffect(()=>{refresh().catch(()=>setMessage('Não foi possível consultar o histórico importado.'));},[refresh]);
  async function load(after=''){
    setBusy(true);setMessage('');
    try{setPage(await request(`history/${collection}?limit=50&after=${encodeURIComponent(after)}`));}
    catch(e){setPage(null);setMessage(e.message);}
    finally{setBusy(false);}
  }
  async function importHistory(e){
    e.preventDefault();if(busy)return;
    setBusy(true);setMessage('');
    try{
      if(!file||file.size>40*1024*1024)throw new Error('Selecione um pacote criptografado de até 40 MiB.');
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
      for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const result=await request('history/import',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({archive:btoa(binary),passphrase:phrase})});
      setPage(null);await refresh();await onChange();
      setMessage(result.already_imported?'Este pacote já foi importado; nenhum lançamento foi duplicado.':
        'Histórico importado e preservado. A conferência dos saldos ainda é necessária para operar.');
    }catch(error){setMessage(error.message);await refresh().catch(()=>{});}
    finally{setPhrase('');setBusy(false);}
  }
  return <Card><CardHeader><CardTitle>Proprietário — histórico da unidade</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      <p>O histórico é consultado separadamente. Importar não cria vendas ou recebimentos novos.</p>
      <p role="status">{info?.active?.history_complete?'Histórico carregado.':'Nenhum histórico completo carregado.'}
        {info?.import_incomplete?' Carga interrompida: selecione o mesmo pacote para retomar.':''}
        {info?.active&&!info.active.operational_baseline_ready?' Saldos aguardam conferência; novas operações estão bloqueadas.':''}</p>
      <details><summary>Importar ou retomar histórico</summary>
        <p>Use somente o pacote desta unidade, preparado após verificar o backup. Não selecione o backup integral do servidor.</p>
        <form onSubmit={importHistory} className="space-y-3">
          <label className="block">Pacote criptografado da unidade<input type="file" accept=".ganoh" disabled={busy} onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
          <label className="block">Frase de recuperação do histórico<input className="block border rounded p-2 bg-background w-full" type="password" autoComplete="off" value={phrase} minLength={16} maxLength={256} disabled={busy} onChange={e=>setPhrase(e.target.value)}/></label>
          <Button type="submit" disabled={busy||!file||phrase.length<16}>{busy?'Aguarde…':'Importar histórico protegido'}</Button>
        </form>
      </details>
      <div className="flex flex-wrap gap-3 items-end">
        <label>Consultar registros<select className="block border rounded p-2 bg-background" value={collection} disabled={busy} onChange={e=>{setCollection(e.target.value);setPage(null);}}>
          {(info?.collections||['orders']).map(name=><option key={name} value={name}>{labels[name]||name}</option>)}
        </select></label>
        <Button variant="outline" disabled={busy||!info?.active} onClick={()=>load()}>Consultar histórico</Button>
      </div>
      {page&&<div className="overflow-x-auto"><table className="w-full text-sm text-left"><caption>Registros importados — valores originais, sem soma ao caixa local</caption>
        <thead><tr><th>Registro</th><th>Data</th><th>Cliente ou produto</th><th>{collection==='stock'?'Quantidade':'Valor registrado'}</th></tr></thead>
        <tbody>{page.items.map((r,i)=><tr key={historyText(r._id)||i} className="border-b">
          <td className="p-2 break-all">{historyText(r.id)||historyText(r._id)||'—'}</td>
          <td className="p-2">{historyText(r.created_at)||historyText(r.updated_at)||'—'}</td>
          <td className="p-2">{historyText(r.customer_name)||historyText(r.name)||historyText(r.description)||'—'}</td>
          <td className="p-2">{historyText(collection==='stock'?r.quantity:(r.total??r.amount??r.amount_reversed??r.credit)).replace('.',',')||'—'}</td>
        </tr>)}</tbody></table>{!page.items.length&&<p>Nenhum registro nesta coleção.</p>}
        {page.next_cursor&&<Button variant="outline" disabled={busy} onClick={()=>load(page.next_cursor)}>Próxima página</Button>}</div>}
      {message&&<p role="status">{message}</p>}
    </CardContent></Card>;
}
