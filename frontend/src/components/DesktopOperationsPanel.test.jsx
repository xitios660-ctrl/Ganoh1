import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import DesktopOperationsPanel from './DesktopOperationsPanel';
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container,request;
beforeEach(()=>{
 container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
 let id=0;Object.defineProperty(global,'crypto',{configurable:true,value:{randomUUID:()=>`fixture-${++id}`}});
 request=jest.fn(async(path)=>path==='status'?{shifts:[],active_shift:null}:path==='catalog'?{items:[{sku:'lanche',quantity:5,version:2}]}:{cash_cents:0});
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
test('opening a zero-count shift sends no artificial cash deposit',async()=>{
 await act(async()=>root.render(<DesktopOperationsPanel request={request} onChange={jest.fn()}/>));
 await act(async()=>container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 const post=request.mock.calls.find(([_path,options])=>options?.method==='POST');
 const body=JSON.parse(post[1].body);
 expect(body.kind).toBe('cash.open');expect(body.data.counted_cents).toBe(0);
 expect(body.data.amount_cents).toBeUndefined();
});
