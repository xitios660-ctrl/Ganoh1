import React,{act} from 'react';import {createRoot} from 'react-dom/client';import OwnerOverviewPage from './OwnerOverviewPage';
global.IS_REACT_ACT_ENVIRONMENT=true;
test('unconfigured owner hosting cannot silently connect to production',async()=>{
 delete process.env.REACT_APP_SYNC_ORIGIN;
 const box=document.createElement('div');document.body.appendChild(box);const root=createRoot(box);global.fetch=jest.fn();
 try{await act(async()=>root.render(<OwnerOverviewPage/>));expect(box.textContent).toContain('Painel aguardando configuração');expect(global.fetch).not.toHaveBeenCalled();}
 finally{await act(async()=>root.unmount());box.remove();}
});

test('owner sees confirmed totals, unknown offline count and scoped stock after login',async()=>{
 process.env.REACT_APP_SYNC_ORIGIN='https://central.example';
 const box=document.createElement('div');document.body.appendChild(box);const root=createRoot(box);
 global.fetch=jest.fn(async(url)=>({ok:true,status:200,json:async()=>url.endsWith('/login')?{access_token:'fixture-session'}:url.endsWith('/tv-accounts')?{accounts:[]}:url.includes('/stock?')?{unit:'runner',items:[{sku:'a',name:'Lanche',quantity:3,version:1}],done:true,created_at:'2026-11-18T00:00:00Z'}:{generated_at:'2026-11-18T00:00:00Z',consolidated:{cash_cents:1000,revenue_cents:1000,expense_cents:0,receivable_cents:0,cash_variance_cents:0,result_cents:1000},units:[{unit:'runner',cash_cents:1000,revenue_cents:1000,expense_cents:0,receivable_cents:0,stale:true,conflicts:0,cash_reviews:0,last_sync_at:null,local_pending:null}]}}));
 try{
  await act(async()=>root.render(<OwnerOverviewPage/>));
  const inputs=box.querySelectorAll('input');
  await act(async()=>{const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(inputs[0],'owner-fixture');inputs[0].dispatchEvent(new Event('input',{bubbles:true}));setter.call(inputs[1],'Fixture-Password-2026');inputs[1].dispatchEvent(new Event('input',{bubbles:true}));});
  await act(async()=>box.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(box.textContent).toContain('Somente operações confirmadas');expect(box.textContent).toContain('desconhecida pelo servidor');expect(box.textContent).toContain('Sem contato recente');
  const stock=Array.from(box.querySelectorAll('button')).find(b=>b.textContent==='Ver estoque de RUNNER');
  await act(async()=>stock.click());expect(box.textContent).toContain('Lanche: 3');
  const login=global.fetch.mock.calls.find(([url])=>url.endsWith('/login'));expect(login[1].credentials).toBe('omit');expect(login[1].redirect).toBe('error');
  // An older response must not repopulate another owner's cleared session.
  let finish;global.fetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  await act(async()=>Array.from(box.querySelectorAll('button')).find(b=>b.textContent==='Atualizar dados').click());
  await act(async()=>Array.from(box.querySelectorAll('button')).find(b=>b.textContent==='Sair').click());
  await act(async()=>finish({ok:true,status:200,json:async()=>({units:[],consolidated:{revenue_cents:999999},generated_at:'2026-11-18T00:00:00Z'})}));
  global.fetch.mockImplementation(async url=>url.endsWith('/login')?({ok:true,json:async()=>({access_token:'different-owner-session'})}):new Promise(()=>{}));
  await act(async()=>box.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(box.textContent).not.toContain('Somente operações confirmadas');

 }finally{await act(async()=>root.unmount());box.remove();delete process.env.REACT_APP_SYNC_ORIGIN;}
});
