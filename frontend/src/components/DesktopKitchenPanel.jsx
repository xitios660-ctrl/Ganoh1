import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Button} from './ui/button';
import {Card,CardContent,CardHeader,CardTitle} from './ui/card';
const labels={received:'Recebido',preparing:'Preparando',ready:'Pronto',delivered:'Entregue'};
const next={received:'preparing',preparing:'ready',ready:'delivered'};
export default function DesktopKitchenPanel({request,onBack}) {
 const [orders,setOrders]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);const retry=useRef(null);
 const refresh=useCallback(async()=>{try{const r=await request('orders');setOrders(r.items);}catch(e){setError(e.message);}},[request]);
 useEffect(()=>{refresh();const timer=setInterval(refresh,3000);return()=>clearInterval(timer);},[refresh]);
 async function advance(order){if(busy)return;setBusy(true);setError('');try{
  if(!retry.current)retry.current={operation_id:crypto.randomUUID(),kind:'order.status',data:{business_id:crypto.randomUUID(),sale_id:order.sale_id,base_version:order.version,status:next[order.status]}};
  await request('commerce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(retry.current)});retry.current=null;await refresh();
 }catch(e){if(e.status>=400&&e.status<500&&e.status!==408)retry.current=null;setError(e.message);}finally{setBusy(false);}}
 return <main className="max-w-5xl mx-auto p-6 space-y-4"><header className="flex justify-between"><h1 className="text-3xl font-bold text-orange-500">GANOH — cozinha local</h1>{onBack&&<Button variant="outline" onClick={onBack}>Voltar ao caixa</Button>}</header>
 <p>Pedidos persistidos neste computador. Alterações offline aguardam confirmação central; conflitos precisam de revisão.</p>{error&&<p role="alert" className="text-red-500">{error}</p>}
 {orders.length===0&&<p>Nenhum pedido local.</p>}{orders.map(o=><Card key={o.sale_id}><CardHeader><CardTitle>{o.customer_name} • {labels[o.status]||o.status}</CardTitle></CardHeader><CardContent className="space-y-2"><ul>{o.items.map((i,index)=><li key={i.sku+'-'+index}>{i.quantity} × {i.name}</li>)}</ul><p className="text-xs">Pedido {o.sale_id} • versão {o.version} • {o.sync_state==='synced'?'Confirmado no servidor':o.sync_state==='conflict'?'Conflito — revisão necessária':'Alteração local pendente'}</p>{next[o.status]&&<Button disabled={busy||(retry.current&&retry.current.data.sale_id!==o.sale_id)} onClick={()=>advance(o)}>{retry.current?.data.sale_id===o.sale_id?'Repetir mesma alteração':`Marcar ${labels[next[o.status]]}`}</Button>}</CardContent></Card>)}
 </main>;
}
