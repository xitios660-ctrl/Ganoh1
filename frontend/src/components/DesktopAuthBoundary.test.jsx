import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import DesktopAuthBoundary from './DesktopAuthBoundary';
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container;
beforeEach(()=>{container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test('financial content stays hidden until an authenticated local account exists',async()=>{
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>({required:true,configured:false,actor:null})}));
 await act(async()=>root.render(<DesktopAuthBoundary><p>Private cash balance</p></DesktopAuthBoundary>));
 expect(container.textContent).not.toContain('Private cash balance');
 expect(container.textContent).toContain('Não há senha padrão');
 expect(container.querySelector('input[type=password]').minLength).toBe(12);
});
test('authenticated owner can see content and logout removes it',async()=>{
 let identity={actor_id:'owner-fixture',username:'owner-demo',role:'owner'};
 global.fetch=jest.fn(async(url)=>{if(url.endsWith('logout'))identity=null;return {ok:true,json:async()=>({required:true,configured:true,actor:identity})};});
 await act(async()=>root.render(<DesktopAuthBoundary><p>Private cash balance</p></DesktopAuthBoundary>));
 expect(container.textContent).toContain('Private cash balance');
 await act(async()=>container.querySelector('button').click());
 expect(container.textContent).not.toContain('Private cash balance');
 expect(container.textContent).toContain('Entre com sua conta');
});
