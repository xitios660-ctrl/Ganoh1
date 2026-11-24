import React, {useEffect, useState} from 'react';
import {Button} from './ui/button';
import {Card, CardContent, CardHeader, CardTitle} from './ui/card';

// Mounted only in the separate owner homologation build. Never stores credentials.
export default function DesktopTVAccessPanel({origin, token, units}) {
  const [accounts,setAccounts]=useState([]),[username,setUsername]=useState(''),[password,setPassword]=useState('');
  const [selected,setSelected]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    fetch(origin+'/api/sync/v1/owner/tv-accounts',{headers:{Authorization:'Bearer '+token},credentials:'omit',redirect:'error',signal:controller.signal})
      .then(async r=>{if(!r.ok)throw new Error('Não foi possível consultar os acessos de TV.');return r.json();})
      .then(b=>{if(!Array.isArray(b.accounts))throw new Error('Resposta incompatível dos acessos de TV.');if(!controller.signal.aborted)setAccounts(b.accounts);})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[origin,token,revision]);
  async function write(path,body) {
    const r=await fetch(origin+'/api/sync/v1/owner/tv-accounts'+path,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},credentials:'omit',redirect:'error',body:JSON.stringify(body)});
    if(!r.ok)throw new Error(r.status===422?'Confira usuário, senha de pelo menos 12 caracteres diferente da senha do proprietário e unidades.':'Acesso recusado ou servidor indisponível.');
  }
  async function create(e){e.preventDefault();setBusy(true);setError('');try{await write('',{username,password,units:selected.filter(u=>units.includes(u))});setUsername('');setSelected([]);}catch(e){setError(e.message);}finally{setPassword('');setBusy(false);setRevision(n=>n+1);}}
  async function revoke(id){setBusy(true);setError('');try{await write('/'+encodeURIComponent(id)+'/revoke',{});}catch(e){setError(e.message);}finally{setBusy(false);setRevision(n=>n+1);}}
  return <Card><CardHeader><CardTitle>Acessos exclusivos para Android TV</CardTitle></CardHeader><CardContent className="space-y-3">
    <p>Homologação: a TV consulta somente as unidades escolhidas. Crie uma senha diferente da sua; revogar encerra suas sessões na central.</p>
    <form onSubmit={create} className="space-y-3">
      <label className="block">Usuário da TV<input className="block border rounded p-2 bg-background w-full" value={username} onChange={e=>setUsername(e.target.value)} pattern="[a-z0-9._\-]{3,64}" autoCapitalize="none" autoCorrect="off" spellCheck={false} autoComplete="off" required/></label>
      <label className="block">Senha exclusiva da TV<input className="block border rounded p-2 bg-background w-full" type="password" value={password} onChange={e=>setPassword(e.target.value)} minLength={12} maxLength={256} autoComplete="new-password" required/></label>
      <fieldset><legend>Unidades que essa TV pode consultar</legend>{units.map(unit=><label className="block" key={unit}><input type="checkbox" checked={selected.includes(unit)} onChange={e=>setSelected(current=>e.target.checked?[...current,unit]:current.filter(u=>u!==unit))}/>{unit==='runner'?'RUNNER':'GYM LONDRES'}</label>)}</fieldset>
      <Button type="submit" disabled={busy||!selected.some(u=>units.includes(u))}>Criar acesso da TV</Button>
    </form>
    <ul>{accounts.map(account=><li key={account.account_id} className="py-2">{account.username} • {account.units.join(', ')} • {account.revoked?'Revogado':<Button variant="outline" disabled={busy} onClick={()=>revoke(account.account_id)}>Revogar {account.username}</Button>}</li>)}</ul>
    {error&&<p role="alert">{error}</p>}
  </CardContent></Card>;
}
