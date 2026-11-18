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
