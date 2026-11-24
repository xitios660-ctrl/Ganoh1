"""Real Chromium fixture import through the Windows React/loopback API. No Atlas."""
import hashlib
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
import uvicorn
from bson import BSON, Decimal128
from bson.timestamp import Timestamp
from playwright.sync_api import sync_playwright
from backend.data_bridge.archive import Writer,new_file
from backend.data_bridge.unit_export import UNIT_FORMAT
from desktop.local_api import create_local_app
from desktop.offline_store import OfflineJournal


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);phrase='Fixture-history-browser-phrase-2026'
        raw=BSON.encode({'_id':'fixture-history','id':'Pedido antigo fictício','store':'runner',
            'customer_name':'Cliente fictício','total':Decimal128('10.25'),'created_at':'2026-11-21T16:00:00Z'})
        path=folder/'history.ganoh'
        with new_file(path) as output:
            writer=Writer(output,phrase,kind=UNIT_FORMAT);page=writer.page(raw)
            writer.finish({'archive_id':writer.id,'unit':'runner','source_database':'fixture-source',
                'read_timestamp':Timestamp(100,1),'collections':[{'name':'orders','count':1,
                'sha256':hashlib.sha256(raw).hexdigest(),'pages':[page]}]})
        journal=OfflineJournal(folder/'encrypted.sqlite','runner',encryption_key=secrets.token_bytes(32))
        token=secrets.token_hex(32)
        app=create_local_app(journal,token,frontend=Path('frontend/build'),require_operator=True,interval=100)
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
        origin='http://127.0.0.1:'+str(listener.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                try:
                    page=browser.new_page(viewport={'width':1280,'height':900})
                    unexpected=[]
                    def route(request):
                        if urlsplit(request.request.url).netloc==urlsplit(origin).netloc:
                            request.continue_(headers={**request.request.all_headers(),'Authorization':'Bearer '+token})
                        else:unexpected.append(request.request.url);request.abort()
                    page.route('**/*',route);page.goto(origin+'/desktop-demo')
                    page.get_by_label('Usuário local',exact=True).fill('fixture-owner')
                    page.get_by_label('Senha local',exact=True).fill('Fixture-owner-password-2026')
                    page.get_by_role('button',name='Criar proprietário',exact=True).click()
                    page.get_by_text('Proprietário — histórico da unidade',exact=True).wait_for()
                    page.get_by_text('Importar ou retomar histórico',exact=True).click()
                    page.get_by_label('Pacote criptografado da unidade',exact=True).set_input_files(str(path))
                    recovery=page.get_by_label('Frase de recuperação do histórico',exact=True)
                    recovery.fill(phrase)
                    page.get_by_role('button',name='Importar histórico protegido',exact=True).click()
                    page.get_by_text('Histórico importado e preservado.',exact=False).wait_for()
                    assert recovery.input_value()==''
                    page.get_by_role('button',name='Consultar histórico',exact=True).click()
                    page.get_by_role('cell',name='Cliente fictício',exact=True).wait_for()
                    assert page.get_by_role('cell',name='10,25',exact=True).count()==1
                    assert journal.status()['pending']==0
                    stored=' '.join(page.evaluate('Object.values(localStorage)'))
                    assert phrase not in stored and 'Cliente fictício' not in stored and 'fixture-history' not in stored
                    assert not unexpected,unexpected
                    page.get_by_text('Proprietário — histórico da unidade',exact=True).scroll_into_view_if_needed()
                    page.screenshot(path='/tmp/ganoh-history-owner-fixture.png')
                    page.reload()
                    page.get_by_role('button',name='Consultar histórico',exact=True).click()
                    page.get_by_role('cell',name='Pedido antigo fictício',exact=True).wait_for()
                    print('PASS: browser encrypted history import, exact value, reload, no new outbox, no external requests')
                finally:browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=20);listener.close()
            assert not thread.is_alive()


if __name__=='__main__':main()
