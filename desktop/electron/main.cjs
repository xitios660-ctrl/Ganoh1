const { app, BrowserWindow, dialog, session } = require('electron');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const path = require('node:path');
const fs = require('node:fs');
let backend;
let closing = false;
if (!app.requestSingleInstanceLock()) app.quit();
else app.whenReady().then(async () => {
  try {
    const binding = path.join(app.getPath('userData'), 'installation.json');
    let unit;
    if (fs.existsSync(binding)) {
      unit = JSON.parse(fs.readFileSync(binding, 'utf8')).unit;
      if (!['runner', 'gym-londres'].includes(unit)) throw new Error('Invalid installation unit');
    } else {
      const choice = await dialog.showMessageBox({type: 'question', title: 'GANOH — demonstração', message: 'Vincule esta instalação à unidade de demonstração', buttons: ['RUNNER', 'GYM LONDRES', 'Cancelar'], cancelId: 2});
      if (choice.response === 2) return app.quit();
      unit = choice.response === 0 ? 'runner' : 'gym-londres';
      fs.mkdirSync(path.dirname(binding), {recursive: true});
      fs.writeFileSync(binding, JSON.stringify({unit}), {flag: 'wx'});
    }
    const token = randomBytes(32).toString('hex');
    backend = spawn(path.join(process.resourcesPath, 'backend', 'ganoh-local.exe'), ['--unit', unit, '--demo'], {windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']});
    backend.stderr.on('data', () => {}); // Drain without logging sensitive diagnostics.
    backend.stdin.end(token + '\n');
    const port = await new Promise((resolve, reject) => {
      let buffer = '';
      const timer = setTimeout(() => reject(new Error('O serviço local não iniciou no prazo.')), 30000);
      backend.once('error', reject);
      backend.once('exit', () => reject(new Error('O serviço local encerrou durante a inicialização.')));
      backend.stdout.on('data', chunk => {
        buffer += chunk;
        if (buffer.includes('\n')) {
          try { const value = JSON.parse(buffer.split('\n')[0]); if (!Number.isInteger(value.port) || value.port < 1 || value.port > 65535) throw new Error(); clearTimeout(timer); resolve(value.port); }
          catch { clearTimeout(timer); reject(new Error('Resposta inválida do serviço local.')); }
        }
      });
    });
    const origin = `http://127.0.0.1:${port}`;
    // Session token stays in the privileged main process, never in React/storage.
    session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
      if (details.url.startsWith(origin + '/')) details.requestHeaders.Authorization = 'Bearer ' + token;
      callback({requestHeaders: details.requestHeaders});
    });
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
    const window = new BrowserWindow({width: 1200, height: 850, webPreferences: {contextIsolation: true, nodeIntegration: false, sandbox: true, devTools: !app.isPackaged}});
    window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
    window.webContents.on('will-navigate', (event, url) => {if (new URL(url).origin !== origin) event.preventDefault();});
    backend.once('exit', () => {if (!closing) {dialog.showErrorBox('GANOH', 'Serviço local interrompido. Reabra o aplicativo; as vendas salvas permanecem no computador.'); app.quit();}});
    // Readiness endpoint requires a fresh session; bounded retry handles socket startup.
    let ready = false;
    for (let i = 0; i < 50; i++) {
      try { const response = await fetch(origin + '/api/local/auth', {headers: {Authorization: 'Bearer ' + token}}); if (response.ok) {ready = true; break;} } catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (!ready) throw new Error('Serviço local indisponível.');
    await window.loadURL(origin + '/desktop-demo');
  } catch {dialog.showErrorBox('GANOH', 'Não foi possível iniciar a demonstração. Verifique a instalação e a chave protegida do Windows.'); app.quit();}
});
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => {closing = true; if (backend && !backend.killed) backend.kill();});
