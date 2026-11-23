import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import DesktopHistoryPanel,{historyText} from './DesktopHistoryPanel';

global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container,request;
const status={active:{history_complete:true,operational_baseline_ready:false},collections:['orders','prazo_payment_reversals']};
beforeEach(()=>{
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  request=jest.fn(async path=>path==='history'?status:{items:[],next_cursor:null});
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
const button=text=>Array.from(container.querySelectorAll('button')).find(b=>b.textContent===text);
it('shows baseline hold and follows the generation cursor without summing imported money',async()=>{
  request.mockImplementation(async path=>path==='history'?status:path.includes('after=gen%3Akey')?
    {items:[],next_cursor:null}:{items:[{_id:{$oid:'fixture-id'},customer_name:'Fixture client',total:{$numberDecimal:'9007199254740993.25'}}],next_cursor:'gen:key'});
  await act(async()=>root.render(<DesktopHistoryPanel request={request}/>));
  expect(container.textContent).toContain('novas operações estão bloqueadas');
  await act(async()=>button('Consultar histórico').click());
  expect(container.textContent).toContain('9007199254740993,25');
  await act(async()=>button('Próxima página').click());
  expect(request).toHaveBeenCalledWith('history/orders?limit=50&after=gen%3Akey');
  expect(container.textContent).toContain('Nenhum registro nesta coleção');
  expect(historyText({$numberDecimal:'10.25'})).toBe('10.25');
});
it('imports only encrypted file bytes and clears recovery phrase after response loss',async()=>{
  request.mockImplementation(async path=>{if(path==='history/import')throw new Error('Resposta interrompida');return status;});
  await act(async()=>root.render(<DesktopHistoryPanel request={request}/>));
  const file=container.querySelector('input[type=file]');
  Object.defineProperty(file,'files',{value:[{size:3,arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer}]});
  const phrase=container.querySelector('input[type=password]');
  await act(async()=>{
    file.dispatchEvent(new Event('change',{bubbles:true}));
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(phrase,'Fixture-Recovery-Phrase-2026');
    phrase.dispatchEvent(new Event('input',{bubbles:true}));
  });
  await act(async()=>container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  const call=request.mock.calls.find(c=>c[0]==='history/import');
  expect(JSON.parse(call[1].body)).toEqual({archive:'AQID',passphrase:'Fixture-Recovery-Phrase-2026'});
  expect(phrase.value).toBe('');
  expect(container.textContent).toContain('Resposta interrompida');
  expect(localStorage.length).toBe(0);
});
