> Estado atualizado da implementação: [relatório de 18/11/2026](CODEX_WINDOWS_PROGRESS_2026-11-18.md) e [demonstração Windows](../desktop/DEMONSTRATION.md). O plano/auditoria abaixo é histórico; há agora API central isolada, snapshots de catálogo/estoque, revisão limitada, API local, SQLCipher/DPAPI e build Electron demonstrativo. Isso não equivale à migração comercial concluída.

# GANOH Windows / offline-first: plano de migração e riscos (isolado da produção)

**Situação: protótipo de arquitetura, não liberado para atendimento.**
Branch: `feature/windows-offline-ganoh-2026`. O Render, o código de `main` e o MongoDB `ganoh_production` NÃO são modificados por este trabalho.

## Auditoria baseada no código atual

- Frontend: React/CRA, React Router, fluxo de cardápio (`MenuPage`), cozinha (`KitchenPage`), gestor (`GestorPage`), estoque e contas a prazo.
- Backend: FastAPI (`backend/server.py` com roteadores adicionais), Motor/MongoDB. Em produção, `backend/render_app.py` monta a mesma interface web.
- `frontend/src/utils/offline.js`: fila de pedidos em `localStorage` e `POST /api/orders/sync`; cache de cardápio com validade de 24 horas.
- `frontend/src/services/offlineService.js`: outra fila de pedidos na MESMA chave `ganoh_offline_orders`, mas com outro esquema de dados e outro fluxo (`POST /api/orders` pedido a pedido).
- `frontend/src/components/OfflineBanner.js` e `MenuPage.js` acionam fluxos diferentes. A ausência de resposta ao POST pode levar a um segundo envio mesmo quando o servidor salvou o pedido.
- `backend/server.py`: `/api/orders/sync` chama `create_order` para cada item sem consulta/índice exclusivo do `offline_id` antes de modificar crédito, pedido e estoque.
- `frontend/public/service-worker.js`: explicitamente **network only**, sem cache de execução offline, para respeitar as regras atuais de suspensão.
- Há escritas MongoDB em várias operações; simplesmente trocar a conexão por SQLite NÃO preservará todas as regras de negócio.

**Conclusão:** o modo offline atual é parcial e não tem garantia de idempotência financeira. Não ativar envio automático de operações financeiras do novo protótipo contra a API de produção.

## Arquitetura alvo

```text
PC Runner (Windows)                         PC GYM Londres (Windows)
Electron + React (UI atual)                  Electron + React (UI atual)
        |                                              |
FastAPI local (127.0.0.1)                    FastAPI local (127.0.0.1)
SQLite criptografado, WAL                    SQLite criptografado, WAL
Fila de operações imutáveis                  Fila de operações imutáveis
        |                                      |
        +------------- HTTPS/TLS -------------+
                           |
             API central de sincronização
             Autenticação por dispositivo + unidade
             Inbox idempotente/índices únicos
                           |
               MongoDB Atlas (central)
                           |
             Gestor no celular (PWA/web)
        Unidade + consolidado + última sincronização
```

O aplicativo Windows **não** terá credenciais do Atlas; o servidor central será o único componente autorizado a acessá-lo. O backend central poderá migrar para VPS, Railway, Fly.io ou infraestrutura gerenciada após avaliação de custo, backups, disponibilidade e política de recuperação. Render atual permanece como serviço de produção até aceite explícito.

## Protocolo de sincronização necessário

1. Cada instalação recebe `device_id`, `unit` fixa e identidade revogável; toda operação recebe UUID e sequência local monotônica. Não aceitar a unidade fornecida pelo cliente sem compará-la à identidade autenticada.
2. SQLite grava **dados da operação + outbox** na mesma transação, com valores monetários em **centavos inteiros**. Um reinício não altera UUIDs nem perde itens pendentes.
3. `POST /api/sync/v1/batch` (novo endpoint, inicialmente em homologação): corpo com `device_id`, `operation_id`, `unit`, `kind`, `payload`, `payload_hash`, versão-base. Resposta por item: `applied` ou `already_applied` com mesmo recibo, `conflict` ou `retryable_error`.
4. **No MongoDB**, criar inbox com índice único `(device_id, operation_id)`; aplicar recibo + efeito financeiro/estoque em uma transação atômica, ou outro desenho equivalente e comprovadamente idempotente. Repetições com hash diferente são rejeitadas. Nunca recalcular valor em reais de ponto flutuante para evitar arredondamento.
5. O cliente confirma e retém o recibo somente após a resposta autenticada conter UUID, unidade e hash correspondentes. Uma resposta perdida faz repetir o MESMO UUID, nunca criar nova venda.
6. `GET /api/sync/v1/changes?cursor=...` fornece snapshots e alterações confirmadas por unidade, com versões e paginação. Cursor e confirmação duráveis. O painel do dono informa horário da última sincronização de cada loja; números locais não sincronizados ficam identificados como provisórios.
7. **Conflitos:** estoque é conciliado pelo servidor com revisão de versão (não sobrescrever silenciosamente; fila de resolução manual); baixa de prazo exige idempotência e registro de quem confirmou; PIX offline é **pendente de verificação**, jamais liquidado automaticamente apenas por comprovante; estorno é novo evento auditável, não exclusão.
8. Sincronização respeita pagamentos em ordem causal por cliente, taxas de cartão, eventos com origem e datas UTC + timezone do Brasil na exibição. Rejeitar operações de uma unidade com dados de outra.

## Segurança

- Aplicativo empacotado com Electron: `contextIsolation`, `sandbox`, `nodeIntegration=false`, CSP, URLs internas controladas; processo local apenas em loopback com autenticação de sessão, sem porta exposta em LAN.
- SQLite local: **criptografia em repouso** (SQLCipher ou esquema equivalente com chave protegida via DPAPI/Windows Credential Manager), backups locais cifrados, acesso restrito à conta Windows e proteção de recuperação.
- O módulo `desktop/offline_store.py` desta primeira etapa é **apenas um protótipo funcional de persistência**, NÃO criptografa os dados e NÃO faz integração financeira. É proibido usar com dados reais antes de implementar segurança e sincronização central.
- Segredos, senhas e tokens jamais devem ir para o código, CI, repositório ou instalador. Tokens de cada PC devem poder ser revogados. Recomenda-se renovar credenciais expostas em conversas/imagens anteriores antes da distribuição.
- Devem existir auditoria de operações e segregação por unidade e permissões no backend.

## Backup antes de QUALQUER migração

1. Congelar escopo e registrar contagens de `orders`, `order_history`, `menu`, `expenses`, `prazo_*`, `stock`, `pix_adjustments`, `tenants`, `recovery_runs` no MongoDB original.
2. Executar `mongodump --uri <URI_PRIVADA> --archive=<ARQUIVO_PRIVADO> --gzip` em ambiente autorizado, fora do repositório, sem colocar credenciais em argumentos/logs persistentes. Usar cofre de segredos para credencial e proteger arquivo com criptografia.
3. Gerar manifesto com versão, SHA-256, contagem por coleção e horário; guardar o backup fora do Render e dos PCs, com política de retenção.
4. **Restaurar em cluster isolado de homologação** e verificar índices, contagens, saldos, datas e relatórios. Backup sem teste de restauração não é considerado validado.
5. Somente após aprovação, ensaiar mudanças com dados sanitizados e nunca sobrepor o banco original. Plano de rollback: retornar PCs à versão anterior, desabilitar API nova, manter operações locais pendentes e reconciliar manualmente; não duplicar replay na API antiga.

Nenhum backup foi extraído ou restaurado por esta primeira etapa. Nenhuma migração em produção ocorreu.

## Fases, entregas e critérios de aceite

| Fase | Entrega | Critério / trava |
| --- | --- | --- |
| A | Auditoria e branch isolada | identificar rotas, filas e riscos; `main` intocado |
| B | Núcleo SQLite/Outbox | testes de crash, reenvio, rollback, conflito e segregação por unidade |
| C | API idempotente central em homologação | índice único, autenticação por PC, pagamentos e estoque sem dupla aplicação |
| D | Adaptar FastAPI local + React existente | paridade de cardápio, cozinha, caixa, prazo, estoque, despesas, relatórios; sem acesso Atlas no PC |
| E | Electron + empacotamento Windows | instalador .exe assinado, atualização segura, logs e modo offline real |
| F | Servidor central alternativo + painel mobile | dados por loja/consolidado, timestamp e pendências; backup e restore comprovados |
| G | Ensaios de aceite | desligar rede no meio do POST, religar, reiniciar PC, dois PCs, perder resposta, reenvio 10x, conflitos, estorno, saldo, caixa |
| H | Piloto + ativação | aprovação explícita, reconciliação financeira por loja e procedimento de rollback |

### Testes críticos obrigatórios

- 2 PCs Windows diferentes; loja e instalação vinculadas de forma permanente.
- Vendas em PIX, dinheiro, cartão e prazo, inclusive tentativas de duplicidade e cancelamento.
- Falha de rede em três momentos: antes da requisição, depois de salvar no servidor e antes de confirmar ao cliente.
- Reinício forçado durante gravação SQLite; `PRAGMA quick_check`, saldo de outbox, ausência de vendas parciais.
- Recebimento a prazo duplicado no mesmo cliente; crédito, cancelamentos e reversões com histórico imutável.
- Estoque concorrente com venda offline nas duas unidades e ajuste manual; nunca mesclar silenciosamente.
- Dados históricos importados de PDF continuam separados de depósitos bancários, e a conta da GYM Londres é reconciliada contra extratos.
- Simulação de restauração do backup, perda do servidor central e janela de internet instável.

## O que está implementado nesta branch

- `desktop/offline_store.py`: SQLite com WAL, integridade, vínculo fixo à unidade, gravação atômica de venda + evento em fila, UUID e hash estáveis, ACKs idempotentes, conflitos preservados e contagem de pendências.
- `desktop/tests/test_offline_store.py`: testes automatizados sem acessar produção.
- `.github/workflows/ganoh-offline-tests.yml`: testes para Windows e Linux.

**Ainda NÃO implementado:** API central idempotente, criptografia local, autenticação desktop, interface integrada, instalador Windows, tarefas de pagamentos/estoque offline, sincronização ativa, backup real e testes físicos dos 2 PCs. Não anunciar software pronto nem compartilhar executável falso.
