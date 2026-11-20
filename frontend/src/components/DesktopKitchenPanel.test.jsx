import React,{act} from 'react';import {createRoot} from 'react-dom/client';import DesktopKitchenPanel from './DesktopKitchenPanel';
global.IS_REACT_ACT_ENVIRONMENT=true;
test('kitchen advances a versioned order without exposing financial totals',async()=>{
 const box=document.createElement('div');document.body.appendChild(box);const root=createRoot(box);
 let current={sale_id:'fixture-sale',customer_name:'Cliente fictício',status:'received',version:1,sync_state:'pending',items:[{sku:'a',name:'Lanche',quantity:1}]};
 Object.defineProperty(global,'crypto',{configurable:true,value:{randomUUID:()=> 'fixture-id'}});
 const request=jest.fn(async(_path,opts)=>{if(opts){current={...current,status:'preparing',version:2};return {state:'pending'};}return {items:[current]};});
 try{await act(async()=>root.render(<DesktopKitchenPanel request={request}/>));
 expect(box.textContent).not.toContain('R$');
 await act(async()=>box.querySelector('button').click());
 const data=JSON.parse(request.mock.calls.find(([_p,options])=>options)[1].body);
 expect(data.kind).toBe('order.status');expect(data.data.base_version).toBe(1);expect(data.data.status).toBe('preparing');
 expect(box.textContent).toContain('Preparando');
 }finally{await act(async()=>root.unmount());box.remove();}
});
