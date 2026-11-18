# Relatório técnico — 18/11/2026

## Fase 1 — auditoria inicial e verificação do núcleo

Confirmados: branch `feature/windows-offline-ganoh-2026` no commit inicial `24d9811`, issue #5 aberta e PR #6 aberto como rascunho, base `main`. Inventário de 263 arquivos versionados, leitura do núcleo SQLite, coordenador, documentação, workflow e inspeção dos caminhos de venda/sincronização e testes. Esta é auditoria inicial dos caminhos críticos; não constitui revisão linha a linha dos módulos comerciais completos.

Pronto no protótipo: transação SQLite venda/outbox, UUID/hash, vínculo de unidade, persistência entre aberturas, ACK validado, conflito retido, 15 testes originais passando. Ausentes: autenticação de instalação, criptografia e integração comercial. A API legacy `/orders/sync` chama `create_order` sem deduplicação central; crédito, venda e estoque têm escritas separadas. Os dois mecanismos localStorage têm formatos divergentes. Não foram alterados neste incremento, pois atendem ao sistema atual e precisam de migração controlada.

React/CRA e telas comerciais existentes serão preservados. Electron é a escolha inicial documentada em `backend/sync_v1/README.md`; tamanho e consumo precisam de medição antes de confirmar empacotamento.

Testes HTTP legados incluem destinos externos e operações de escrita/exclusão: não executados. Testes Node: 11 casos de inbound WhatsApp passaram; suíte auth não carregou por falta de `@whiskeysockets/baileys`. Não é falha atribuída à nova API e não indica validação completa do WhatsApp.

## Fase 2 — primeira implementação, parcial

Arquivos:
- `backend/sync_v1/service.py`: fábrica FastAPI isolada, autenticação por hash de token, dispositivo revogável, unidade fixa, validação UUID/hash, índices únicos e transação snapshot/majority.
- `backend/sync_v1/tests/test_integration.py`: ensaios com MongoDB real descartável, incluindo concorrência e falha injetada.
- `backend/sync_v1/requirements-test.txt`, `backend/sync_v1/README.md`: dependências mínimas e contrato/limites/reprodução.
- `desktop/sync_transport.py`, `desktop/tests/test_sync_transport.py`: transporte HTTPS, sem redirects, compatível com o coordenador existente.
- `.github/workflows/ganoh-offline-tests.yml`: dependência do transporte e job com replica set descartável, além da matriz Windows/Linux existente.

A transação confirma venda em dinheiro, estoque e inbox juntos. Falha intermediária desfaz todos. Reenvio conserva recibo e não duplica efeitos; outro UUID para a mesma venda também não duplica. Preços são validados pelo catálogo e versões de estoque divergentes exigem revisão. PIX/cartão/prazo são preservados como conflito sem liquidação. Não existem recebimentos implementados: bloquear pagamento não equivale a validar módulo financeiro.

Resultados locais Linux: **17 testes desktop e 8 testes de integração MongoDB aprovados**; compilação Python e diff check aprovados. Banco usado: nomes aleatórios `ganoh_sync_test_*`, MongoDB 7 em container local, sem dados reais. Os testes removem seus próprios bancos. GitHub Actions também passou no commit `94484a0`: núcleo/transportes em Windows e Linux, e integração central em Linux com replica set real. Evidência: https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44206906350 . Não houve teste físico de instalação/atualização ou dos dois PCs.

## Limites e próximas entregas

Esta API só aceita bancos `ganoh_sync_test_*` e não está montada na aplicação de produção. As novas coleções não alimentam relatórios legados. Ainda não é correto marcar a fase 2 inteira ou o produto como concluídos.

Próxima etapa: completar snapshots/cursor, provisionamento e revisão auditável de conflitos; adaptar regras comerciais reais de caixa/prazo/estorno com testes de saldos antes de montar API local. Depois, segurança loopback e SQLite cifrado, paridade React, supervisão Python e instalador Electron/PyInstaller com ensaios reais de atualização.

Fases 3–7 não concluídas. Hospedagem alternativa ainda requer comparação atualizada de preços, região, disponibilidade e backup. Não foi solicitada nem realizada migração. Backup de produção/restauração depende de ambiente autorizado e armazenamento protegido, e deve preceder qualquer cutover. Assinatura Windows requer certificado e validação nos dois PCs exige acesso físico ou sessão de homologação autorizada.

Produção, Render, `main` e `ganoh_production` permanecem intocados. Nenhum segredo foi copiado para o código. Não é necessário acesso à produção para continuar a implementação isolada.

PR de revisão: https://github.com/xitios660-ctrl/Ganoh1/pull/6

## Incremento seguinte — demonstração local e snapshots

Implementado na continuação: snapshots imutáveis e paginados de catálogo/estoque com versões, staging/cursor duráveis e retomada no SQLite; revisão auditável `reject`/`retain` com autenticação separada do proprietário; FastAPI local com sessão/origem/host protegidos, tarefa automática de sync, venda em dinheiro e histórico persistente de erros sem segredos; suporte SQLCipher, chave/token via DPAPI Windows, launcher e shell Electron/NSIS de demonstração.

Arquivos principais: `desktop/snapshots.py`, `desktop/local_api.py`, `desktop/windows_secrets.py`, `desktop/launcher.py`, `desktop/electron/*`, `desktop/requirements.txt`, `desktop/DEMONSTRATION.md`, `frontend/src/pages/DesktopDemoPage*`; atualizados `desktop/offline_store.py`, `desktop/sync_transport.py`, `backend/sync_v1/service.py`, testes e workflows. `frontend/src/App.js` seleciona a demonstração somente com flag explícita de build; `index.js` evita o service worker legado nesse modo; `craco.config.js` faz o Jest reconhecer o alias já usado pelo webpack.

Validação local até este registro: 25 testes desktop executados (24 aprovados, DPAPI pulado em Linux), 11 testes MongoDB reais aprovados, 2 testes React aprovados; build React demonstrativo compilado com avisos de hooks preexistentes nas telas legadas. CI Windows e build do instalador serão registrados após execução. `npm ci` padrão encontrou conflito de peers preexistente (React/date-fns/day-picker); instalação com `--legacy-peer-deps` funcionou, sem modificar o lockfile existente.

Limitações explícitas: só snapshot de catálogo/estoque, limite de 1.000 SKUs; revisão rejeita ou mantém conflito sem aplicação financeira; várias vendas no mesmo SKU offline podem exigir revisão por versão. Não há integração local de caixa/prazo/clientes/despesas, revisão visual do proprietário, distribuição assinada, recuperação de chave nem homologação física. Não declarar fases completas. Produção e acesso remoto atual preservados. Procedimento e detalhes em `desktop/DEMONSTRATION.md`.

### Evidências adicionais da continuação

CI no commit `3abe644` aprovado: https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44209529968 . Inclui DPAPI e SQLCipher no Windows, 25 testes desktop sem skips nesse sistema, smoke do launcher real com encerramento forçado e reabertura, matriz Linux, integração MongoDB e testes/build React. Uma execução anterior identificou handle de SQLite aberto no ensaio de chave errada; o fechamento foi corrigido e revalidado, sem suprimir o erro.

Ensaio adicional `desktop/tests/browser_demo_smoke.py` passou em Chromium real no Linux: React compilado → API local HTTP → SQLCipher, venda offline, fechamento/reabertura do backend e reconexão → MongoDB central descartável. Confirmados exatamente uma venda e uma baixa de estoque. Captura visual inspecionada. Esse teste usa transporte central injetado, não implantação HTTPS externa.

Commits principais: `6e335b5` (núcleo), `6fb823a` (React/Electron), `3abe644` (fechamento de conexões). Builds de instalador são disparados apenas na branch isolada; o workflow novo não pôde ser disparado manualmente enquanto ausente da default branch, então foi habilitado por push restrito à branch, sem tocar em main.

Último endurecimento do núcleo: schema local identificado como versão 1, abertura de versão futura recusada sem apagar dados; API local exige UUID canônico explícito para impedir geração acidental em retries. Testes locais atualizados: 27 desktop executados (26 aprovados + DPAPI específico de Windows), 11 MongoDB aprovados e 2 React aprovados. Smoke do executável verifica também HTML/JavaScript React empacotados e CSP.

### Resultado final deste incremento — validado em CI

- Commit de código/testes: [`1bceeb3`](https://github.com/xitios660-ctrl/Ganoh1/commit/1bceeb3).
- [CI Windows/Linux, MongoDB e React aprovada](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44210473042): 27 testes desktop no Windows (incluindo DPAPI/SQLCipher), 26 + 1 skip específico de plataforma no Linux, 11 testes MongoDB e 2 testes React/build.
- [Build Windows e ensaio de instalador aprovados](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44210464162): executável PyInstaller com React empacotado, restart com venda pendente, instalação NSIS silenciosa, reinstalação da mesma versão preservando venda/chave, reabertura e desinstalação mantendo banco/chave.
- [Artefato GANOH-Windows-DEMO-UNSIGNED](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44210464162/artifacts/14385298998): ZIP com instalador `.exe` de demonstração **sem assinatura**, retenção de 7 dias. SHA-256 do artefato ZIP registrado pelo GitHub: `61f4bf4ee1cb74300d39f900f3be11b0a06599af506a54bb6c2eeee7ec33e98c`.
- Ensaio Chromium real repetido com sucesso no código final. SQLite local cifrado, venda offline pela UI, encerramento/reabertura do backend, reconexão e exatamente uma venda/baixa central.

O ensaio NSIS anterior havia concluído a preservação de dados, mas falhou ao limpar a pasta temporária porque a desinstalação ainda rodava em outro processo. A chamada agora usa `_?=` do NSIS para aguardar a desinstalação efetiva; o teste inteiro passou sem ignorar erros de limpeza.

**Estado de entrega:** demonstração local instalável validada por automação, não aplicativo comercial homologado. A CI não substitui interação com Electron em Windows 10/11, teste nos dois PCs, upgrade entre versões distintas, assinatura, backup/recuperação de chaves, provisionamento HTTPS real, caixa/prazo/clientes/despesas e revisão financeira completa. Snapshots e resolução de conflitos continuam parciais conforme limites acima. Nenhuma fase comercial foi declarada concluída; produção permanece intocada e PR #6 em rascunho.

Próximo incremento recomendado: projeção/reserva local de estoque com reconciliação auditável e integração de caixa/recebimentos a prazo com livro financeiro e testes de saldo; em paralelo, homologação interativa do instalador em máquinas de teste, sem substituir as instalações das lojas.

## Continuação autorizada: paridade com o site e núcleo comercial 0.3.0

O proprietário pediu todas as funcionalidades existentes no aplicativo futuro, mantendo o site em operação e sem iniciar o uso real agora. Foi criado `docs/DESKTOP_PARITY.md`, com inventário estático das rotas e matriz de funcionalidades implementadas/parciais/pendentes. Não há declaração de paridade completa.

Arquivos novos: `desktop/business_rules.py`, `desktop/commerce.py`, `desktop/tests/test_commerce.py`, `backend/sync_v1/commerce.py`, `frontend/src/components/DesktopCommercePanel.jsx` e testes, `frontend/src/utils/desktopMoney.js` e testes. Atualizados diário, worker, API local/central, testes de integração/browser/Windows, workflows e versão Electron (0.3.0).

Implementado: livro local balanceado com outbox atômica, vendas em dinheiro compondo receita/caixa, suprimentos, retiradas e despesas com verificação de saldo, clientes com nome normalizado e recebimentos em dinheiro contra dívida existente. Recibo de pagamento é único por unidade, independente do UUID da tentativa. Receber reduz dívida e aumenta caixa sem contar receita duas vezes. A central replica validações, exige permissão financeira explícita por dispositivo e serializa transações de dispositivos da mesma unidade contra overdraft. Erro de confirmação interrompe a fila para preservar causalidade. Schema SQLite 2 adiciona estruturas sem alterar payloads/recibos existentes.

Resultados locais: 35 testes desktop (34 aprovados + DPAPI pulado no Linux), 15 testes MongoDB reais aprovados, 6 testes React aprovados, build compilado com avisos legados, e ensaio Chromium real aprovado com venda + despesa + cliente offline, reinício e sincronização, saldos central/local iguais e sem duplicações. Container de testes atingiu limite de arquivos abertos após sucessivos bancos descartáveis: o fixture local e CI receberam nofile=16384, respeitando o limite do daemon rootless; a suíte foi repetida com sucesso. Nenhuma infraestrutura de produção foi tocada.

Limites: recebimentos exigem dívidas pré-existentes; nesta etapa isso só existe nas fixtures, pois ainda faltam vendas a prazo e snapshots de clientes/saldos. Não conceder crédito fictício para contornar a ausência. Não existem fechamento por turno, papéis individuais locais, estornos, paridade de cozinha/cardápio completo/gestor e integração com relatórios remotos. Livro local inclui eventos provisórios/conflitantes e não deve ser apresentado como consolidado. Central histórica de demonstração não recebe backfill de saldo automático. CI/novo instalador serão registrados após validação.

### Validação final 0.3.0

- Commits: [fd039ba — núcleo financeiro](https://github.com/xitios660-ctrl/Ganoh1/commit/fd039ba) e [1fea038 — interface, testes e matriz de paridade](https://github.com/xitios660-ctrl/Ganoh1/commit/1fea038).
- [CI aprovada Windows/Linux + MongoDB + React](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44214647847): 35 testes desktop aprovados no Windows (34 + DPAPI pulado no Linux), 15 testes de integração central e 6 testes React. Inclui concorrência de retiradas locais e de dois dispositivos da mesma unidade, recibos duplicados por outros UUIDs, rollback financeiro e migração aditiva do schema 1 preservando payload/hash/recibo.
- [Build/instalador 0.3.0 aprovado](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44214639909): executável com React, encerramento/reabertura e instalação/reinstalação/desinstalação silenciosas conservando venda, despesa, cliente, saldo e chave protegida.
- [Artefato ZIP DEMO 0.3.0, sem assinatura](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44214639909/artifacts/14387553487), retenção de 7 dias. SHA-256 do ZIP registrado pelo GitHub: `f8ee11ad43fde16ac8f6083d9eebc0515f8a1a72efedd9f514c56458d806767c`.
- Chromium real no Linux: venda, despesa e cliente offline, fechamento/reabertura e reconexão, uma venda e dois eventos comerciais centrais, saldo local/central de R$ 7,50 e estoque baixado uma única vez. Somente dados fictícios; transporte central injetado no ensaio.

O PR #6 permanece em rascunho. Não houve merge, cópia de dados reais, migração nem implantação em produção. A instrução de deixar todas as funções prontas permanece objetivo de desenvolvimento: **não está concluída**. A matriz `docs/DESKTOP_PARITY.md` registra o que falta, especialmente cozinha/telas originais, estoque projetado, fechamento por turno, novas vendas a prazo/limites, relatórios, autorização individual, backup/recuperação e homologação interativa nos dois PCs. O instalador segue exclusivo para demonstração.

## Incremento 0.4.0 — núcleo operacional ampliado

Implementado: reserva/projeção local de estoque e snapshots com cobertura por UUID/hash; abertura/fechamento de caixa, diferenças bloqueadas e reconciliação auditada; venda a prazo com limite aprovado centralmente, recebimento parcial e recibo único; cozinha local versionada; cadastro/edição de produtos; contas individuais owner/cashier/kitchen e revogação; backup SQLCipher consistente com chave protegida por frase e restauração isolada; CSV provisório. Rede não bloqueia gravação de vendas.

Painel separado do proprietário: login protegido, sessão em memória, escopo de unidades, livro central confirmado, estoque paginado, última sincronização e atraso. Central aceita somente bancos descartáveis; sem deploy e sem integração com números de produção. Pendências locais remotas são desconhecidas.

Arquivos principais: novos desktop/{inventory,operations,orders,auth,backups,reports}.py; alterados offline_store,commerce,snapshots,local_api,launcher,sync_transport e testes; backend/sync_v1/{service,commerce,owner_auth}.py e integração; React Desktop{AuthBoundary,OperationsPanel,KitchenPanel,SecurityPanel,CommercePanel}, DesktopDemoPage e OwnerOverviewPage, testes; Electron main/package, workflow e documentação. Núcleo inicial em commit 524c5b1.

Validação local executada: 56 testes desktop (54 aprovados, 2 específicos de Windows pulados no Linux), 24 testes MongoDB replica set aprovados, 12 testes React aprovados. Build desktop e build separado do proprietário compilados; somente avisos de hooks preexistentes nas telas legadas. Chromium real aprovado: login, abertura, venda/estoque/cozinha/despesa/cliente offline, fechamento/reabertura, sincronização, aprovação de crédito, venda a prazo e recebimento parcial. Resultado central exato: 2 vendas, 11 eventos comerciais, caixa R$11,50, dívida R$6,00, receita R$20,00, estoque 8 de 10. Transporte central injetado no teste; não comprova HTTPS externo.

Limitações: não há paridade integral das telas originais, estornos/cancelamentos, liquidação PIX/cartão, snapshots de clientes/saldos, UI completa de revisão de conflitos, ativação de recuperação, backups automáticos, assinatura, HTTPS homologado ou validação física Win10/11/dois PCs/upgrade entre versões distintas. Auditoria individual é local; central autentica dispositivo. Não considerar aplicativo comercial pronto. Matriz atual em DESKTOP_PARITY.md. Site, main, Render e ganoh_production não alterados. PR #6 continua rascunho. CI Windows e instalador 0.4.0 serão registrados após execução.
