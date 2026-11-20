import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import DesktopTVAccessPanel from './DesktopTVAccessPanel';
global.IS_REACT_ACT_ENVIRONMENT=true;
test('owner provisions an explicitly scoped TV account and revokes it without persisting its password',async()=>{
 const box=document.createElement('div');document.body.appendChild(box);const root=createRoot(box);let created=false,revoked=false;
 global.fetch=jest.fn(async(url,options={})=>{
  if(options.method==='POST'){if(url.endsWith('/revoke'))revoked=true;else created=true;return {ok:true,json:async()=>({})};}
  return {ok:true,json:async()=>({accounts:created?[{account_id:'fixture-id',username:'runner-tv',units:['runner'],revoked}]:[]})};
 });
 try{
  await act(async()=>root.render(<DesktopTVAccessPanel origin="https://central.example" token="fixture-owner-token" units={['runner']}/>));
  const fields=box.querySelectorAll('input');
  await act(async()=>{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(fields[0],'runner-tv');fields[0].dispatchEvent(new Event('input',{bubbles:true}));set.call(fields[1],'Dedicated-TV-Password-2026');fields[1].dispatchEvent(new Event('input',{bubbles:true}));fields[2].click();});
  expect(box.textContent).not.toContain('GYM LONDRES');
  await act(async()=>box.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  const call=global.fetch.mock.calls.find(([,options])=>options?.method==='POST');
  expect(JSON.parse(call[1].body)).toEqual({username:'runner-tv',password:'Dedicated-TV-Password-2026',units:['runner']});
  expect(call[1].redirect).toBe('error');expect(call[1].credentials).toBe('omit');expect(box.querySelector('input[type=password]').value).toBe('');
  await act(async()=>Array.from(box.querySelectorAll('button')).find(b=>b.textContent==='Revogar runner-tv').click());
  expect(box.textContent).toContain('Revogado');
 }finally{await act(async()=>root.unmount());box.remove();}
});
