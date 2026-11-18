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
