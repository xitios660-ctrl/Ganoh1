import React,{createContext,useContext,useEffect,useState,useCallback} from 'react';
import {Button} from './ui/button';
import {Card,CardContent,CardHeader,CardTitle} from './ui/card';
const ActorContext=createContext(null);
export const useDesktopActor=()=>useContext(ActorContext);
export default function DesktopAuthBoundary({children}) {
 const [state,setState]=useState(null),[username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const refresh=useCallback(async()=>{try{const r=await fetch('/api/local/auth');if(!r.ok)throw new Error('Serviço local indisponível');setState(await r.json());}catch(e){setError(e.message);}},[]);
 useEffect(()=>{refresh();const timer=setInterval(refresh,30000);window.addEventListener('focus',refresh);return()=>{clearInterval(timer);window.removeEventListener('focus',refresh);};},[refresh]);
 async function submit(event){event.preventDefault();setBusy(true);setError('');try{
  const r=await fetch(`/api/local/auth/${state.configured?'login':'setup'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
  const data=await r.json();if(!r.ok)throw new Error(data.detail || 'Não foi possível entrar');await refresh();
 }catch(e){setError(e.message);}finally{setPassword('');setBusy(false);}}
 async function logout(){await fetch('/api/local/auth/logout',{method:'POST'});setState({...state,actor:null});}
 if(state && (!state.required || state.actor)) return <ActorContext.Provider value={state.actor}><div className="max-w-5xl mx-auto p-3 flex justify-between"><span>{state.actor?.username} {state.actor?.role==='owner'?'• Proprietário':state.actor?.role==='cashier'?'• Caixa':'• Cozinha'}</span><Button variant="outline" onClick={logout}>Sair da conta local</Button></div>{children}</ActorContext.Provider>;
 return <main className="min-h-screen bg-background text-foreground flex justify-center items-center p-6"><Card className="w-full max-w-lg"><CardHeader><CardTitle>GANOH — acesso local</CardTitle></CardHeader><CardContent className="space-y-4">
  {!state?<p>Conectando ao serviço local…</p>:<><p>{state.configured?'Entre com sua conta cadastrada neste computador. O acesso funciona sem internet.':'Primeira configuração: o proprietário deve criar sua conta neste computador. Não há senha padrão.'}</p>
  <form onSubmit={submit} className="space-y-3"><label className="block">Usuário local<input className="block w-full border rounded p-2 bg-background" value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" minLength={3} maxLength={64} required /></label>
  <label className="block">Senha local<input className="block w-full border rounded p-2 bg-background" type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete={state.configured?'current-password':'new-password'} minLength={state.configured?1:12} maxLength={256} required /></label>
  {!state.configured && <p className="text-sm">Use pelo menos 12 caracteres. Anote em local seguro; recuperação de acesso exige procedimento do proprietário.</p>}
  <Button type="submit" disabled={busy}>{state.configured?'Entrar':'Criar proprietário'}</Button></form></>}
  {error && <p role="alert" className="text-red-500">{error}</p>}
 </CardContent></Card></main>;
}
