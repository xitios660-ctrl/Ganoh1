# GANOH Windows — demonstração offline, somente dados fictícios

O modo desktop é selecionado **no build** com `REACT_APP_DESKTOP_DEMO=true`. O build web normal mantém todas as rotas/telas atuais. A demonstração reutiliza o tema e os componentes React do projeto, mas é uma tela de demonstração dedicada: não constitui paridade visual/funcional completa com o cardápio, cozinha e gestor. O acesso remoto atual do proprietário permanece no sistema existente.

## Fluxo demonstrável

1. Instalar o artefato **DEMO / UNSIGNED** gerado pelo workflow manual `Build GANOH Windows demonstration (unsigned)` na branch de desenvolvimento. Não instalar como substituto do GANOH das lojas.
2. Abrir o atalho, escolher RUNNER ou GYM LONDRES **na primeira abertura**; o vínculo é conservado para próximas aberturas. O banco cifrado também mantém a unidade e um UUID de dispositivo permanente.
3. Selecionar o lanche fictício e salvar venda em dinheiro. Sem servidor configurado, aparece pendente.
4. Fechar e reabrir: a venda continua no histórico local. Nenhum terminal é necessário para o funcionário.
5. Com homologação HTTPS configurada pelo suporte e catálogo correspondente, a tarefa automática tenta a sincronização a cada 10 segundos e ao clicar no botão. Após confirmação autenticada, a venda fica sincronizada. O catálogo fictício precisa existir na homologação com a mesma versão/preço; divergência gera conflito, não uma aprovação silenciosa.

O instalador é gerado por Electron/NSIS e inclui backend PyInstaller + build React. O processo Python fica oculto e somente em `127.0.0.1` numa porta efêmera; a sessão secreta fica no processo principal Electron, enviada ao backend por stdin e adicionada aos pedidos locais. Renderer sem Node, com sandbox/contextIsolation, sem novas janelas/navegação externa. O backend exige sessão, host loopback e origem compatível. Nenhuma credencial Atlas é empacotada.

Os arquivos persistem em `%LOCALAPPDATA%/GANOH-Demo/<unidade>/`. Instalação/atualização não escreve nesse diretório. A chave de 32 bytes e o token central ficam protegidos por **DPAPI do usuário Windows**; o SQLite usa SQLCipher, incluindo WAL. Não há fallback em texto simples no launcher. Se a chave sumir, a inicialização falha sem substituir o banco. Copiar apenas o `.sqlite3` para outro usuário/PC não permite recuperação: política de backup cifrado com recuperação de chaves ainda precisa ser implementada. Não converter automaticamente os protótipos plaintext antigos.

Configuração de suporte (não destinada ao funcionário): `sync.json` contém somente `{"origin":"https://servidor-de-homologacao"}`; `device-token.dpapi` deve ser provisionado com `desktop.windows_secrets.save_secret` na mesma conta Windows. A API central desta branch continua restrita a `ganoh_sync_test_*`. Não configurar o endpoint legado ou produção.

## Snapshots e conflitos

Snapshots de catálogo/estoque são capturados em transação snapshot no MongoDB, imutáveis por geração, paginados em 100 itens, vinculados ao dispositivo/unidade e com expiração de 24h. Limite demonstrativo: 1.000 SKUs. Página + cursor são gravados juntos no SQLite, com staging; o catálogo publicado só muda na última página. Reabertura retoma o cursor. Versões inferiores e snapshots anteriores são rejeitados. O botão de reiniciar download descarta apenas staging/cursor, preservando catálogo publicado, vendas e fila. Não existe CDC incremental completo para todas as coleções.

Operações locais permanecem separadas do snapshot. Múltiplas vendas offline no mesmo SKU ainda podem ter a mesma versão-base e gerar conflitos conservadores após a primeira sincronização; **não há reserva/projeção de estoque operacional completa**. Não alterar UUID para contornar conflitos.

`POST /api/sync/v1/conflicts/review` usa credencial de proprietário separada (`reviewers`, token hash, unidades permitidas, revogável). Exige UUID da revisão, versão esperada, motivo e decisão `reject`/`retain`. Evento auditável e revisão da inbox confirmam juntos; repetir a mesma revisão não cria outro evento. Rejeitar não apaga operação nem altera saldo/estoque. A aprovação com reaplicação financeira, a UI do proprietário para revisar e o download das revisões ao desktop ainda faltam. O recibo de conflito original continua imutável.

## Testes e limites

- `python -m unittest discover -s desktop/tests -v`
- Replica set descartável em 27028: `python -m unittest discover -s backend/sync_v1/tests -v`
- `npm --prefix frontend test -- --watch=false --runInBand --runTestsByPath src/pages/DesktopDemoPage.test.jsx`
- Windows: `python desktop/tests/windows_packaged_smoke.py` (isola LOCALAPPDATA, executa backend, grava, encerra forçado, reabre e verifica dedupe/criptografia).
- Workflow manual também executa smoke sobre o `.exe` PyInstaller antes de montar o instalador.

Instalador sem assinatura: somente homologação. Instalação, reinstalação e desinstalação silenciosas passaram na CI Windows com preservação de dados/chave. Ainda faltam testes interativos da UI Electron, instalação/atualização/desinstalação em Windows 10/11 e nos dois PCs, assinatura, recuperação de chave/backup e atualização assinada com rollback. Caixa, clientes, recebimentos a prazo, despesas e estornos não foram adaptados; PIX/cartão/prazo continuam bloqueados para liquidação. Não liberar atendimento real.

### Ensaio no navegador real

Com dependências Playwright/Chromium disponíveis, build React desktop pronto e o replica set descartável em 27028:

```sh
python -m desktop.tests.browser_demo_smoke
```

Esse ensaio executa Chromium, API local HTTP, SQLCipher e API central com MongoDB real; simula rede indisponível, salva pela UI, encerra/reabre o backend e reconecta. Verifica uma única venda central e baixa única do estoque. A captura usa somente dados fictícios (`/tmp/ganoh-desktop-demo.png`). O transporte central nesse ensaio é injetado com TestClient; não comprova um deploy HTTPS real. Foi executado com sucesso em Linux. Não equivale ao teste da janela Electron no Windows.

O workflow Windows também testa instalação silenciosa, reinstalação da mesma versão e desinstalação preservando dados. A atualização entre versões diferentes e o uso interativo em Windows 10/11 continuam sujeitos à homologação física.

### Artefato validado deste incremento

[Baixar ZIP com instalador `.exe` DEMO sem assinatura](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44210464162/artifacts/14385298998) (retenção de 7 dias, acesso conforme permissões GitHub). [Build e testes aprovados](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44210464162), commit `1bceeb3`. Usar somente em máquina de homologação com dados fictícios. Não é a versão operacional completa e não inclui um servidor HTTPS central já implantado.
