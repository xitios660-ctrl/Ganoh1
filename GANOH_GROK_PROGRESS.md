# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 1 — Auditoria completa (read-only): CONCLUÍDA** em 23/09/2026 ~23:41 BRT (America/Sao_Paulo).  
**ETAPA 2 — Branch de trabalho:** BLOQUEADA — MCP `user-GitHub-xai` autenticado como `xitios660-ctrl` mas retorna **403 Resource not accessible by integration** em `create_branch` e `create_or_update_file`. Sem Contents:write. Relatório local pronto; branch remota NÃO criada. Sem deploy / sem alterar main.

Regras respeitadas nesta sessão: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`).

## Referências
| Item | Valor |
| --- | --- |
| Repo | xitios660-ctrl/Ganoh1 |
| Produção UI | https://ganoh.onrender.com |
| Legacy (read-only) | https://charts-3.emergent.host |
| main SHA auditado | `6805956bfd3f41b385928151c115f3d4d3c7afc1` |
| Clone local | `/workspace/Ganoh1` |

## Branches (estado remoto no momento da auditoria)
| Branch | SHA | Diff vs main |
| --- | --- | --- |
| main | 6805956… | base |
| ganoh/whatsapp-ai | 6805956… (igual main) | vazio — sem commits extras |
| ganoh/continuity-sync | b626374… | +3 arquivos: sync Emergent dry-run, workflow horário, GANOH_PROGRESS.md |
| ganoh/staged-audit | 00f16bd… | +fixes financeiras prazo/PIX/idempotência + GANOH_PROGRESS.md longo |
| ganoh/grok-whatsapp-ai | **não criada** (403 MCP write) | arquivo só em `/workspace/Ganoh1/GANOH_GROK_PROGRESS.md` |

## Estrutura mapeada (main)
```
backend/          FastAPI monolito server.py (~6443 linhas) + routers/ + green_api.py + tests/
frontend/         React 19 + CRACO + GestorPage / WhatsAppTab / Kitchen / Stock
whatsapp/         Baileys Node (server.mjs, auth.mjs) — loopback :8002
scripts/          start_render.py, migrate_mongo.py
tests/            pacote vazio (__init__.py)
memory/PRD.md     histórico de iterações + achados de segurança
render.yaml       serviço Docker ganoh1, autoDeploy=false, flags de manutenção
Dockerfile        multi-stage: frontend build + whatsapp deps + Python appuser
```

### Coleções Mongo usadas no monólito
orders, order_history, stock, stock_movements, menu, adicionais, prazo_customers, prazo_debts, prazo_payments, prazo_partial_payments, prazo_history, cash_drawer_config, cash_withdrawals, cash_credit_topups, pix_adjustments, expenses, daily_sales, monthly_sales, chart_cache, low_stock_list, settings, tenants, deploy_markers.

Coleções Baileys (Node): `baileys_auth`, `baileys_locks`.

## WhatsApp — maturidade (main)
### Stack Baileys (`whatsapp/`)
- Dependência: `@whiskeysockets/baileys` **7.0.0-rc14**, Node ≥22.
- Auth: AES-256-GCM via `WHATSAPP_SESSION_KEY` (≥32 chars) em Mongo (`auth.mjs`).
- Lease exclusivo em `baileys_locks` (anti double-connect em deploy).
- QR: `connection.update` → DataURL base64; status `waiting_qr` / `connected` / `logged_out` / `connection_conflict`.
- Grupos: `groupFetchAllParticipating` + cache 60s; join via invite link.
- Envio: `/sendMessage`, `/sendFileByUpload` protegidos por `WHATSAPP_SEND_ENABLED==='true'`.
- Auth HTTP: header `x-whatsapp-token` com `timingSafeEqual`; bind **127.0.0.1:8002**.
- **NÃO há** `messages.upsert` / listener de mensagens recebidas / bot conversacional / presença AI no Node.
- `syncFullHistory: false`; `getMessage` retorna `undefined`.

### Integração backend (`backend/server.py`)
- Provider: `WHATSAPP_PROVIDER` (`baileys` | `greenapi`); Render yaml fixa `baileys`.
- Proxy gestor: `/api/whatsapp/{connect,status,qr,groups,set-target,join-group}` com `verify_whatsapp_manager`.
- Notificações PIX aprovadas → grupo por loja (`STORE_WHATSAPP_GROUPS`).
- Relatórios: `send_morning_shift_report` (14:00 BRT), `send_daily_sales_report` (22:00 BRT).
- Cobrança prazo via WhatsApp (envio direto / links wa.me).
- `routers/whatsapp.py` e `green_api.py` são legado Green API; **não** incluídos via `include_router` no final do monólito (só prazo/menu/stock/cash/live).

### Frontend
- Aba Gestor `WhatsAppTab.js`: status, QR, connect, grupos, destino, flag `sendingEnabled`.
- Poll a cada 5s quando a aba WhatsApp está ativa (`GestorPage.js`).

### Inicialização em produção
- `scripts/start_render.py`: Baileys **só sobe** se `MIGRATION_PENDING != true` **e** `WHATSAPP_PROVIDER=baileys`.
- Com `MIGRATION_PENDING=true` (estado declarado), o Node WhatsApp **não inicia**; `render_app.py` serve só manutenção 503.

## Flags de segurança (render.yaml / docs)
| Flag | Valor yaml | Efeito |
| --- | --- | --- |
| MIGRATION_PENDING | `"true"` | Manutenção; app de negócio não carrega; Baileys não sobe |
| SCHEDULER_ENABLED | `"false"` | Jobs APScheduler não dão `start()` |
| WHATSAPP_SEND_ENABLED | `"false"` | Node recusa envio (403) |
| SYNC_GESTOR_PASSWORD | `"false"` | Não rotaciona hash do tenant gestor no boot |
| WHATSAPP_PROVIDER | `baileys` | Proxy aponta para loopback |

Jobs registrados (quando scheduler liga): auto-ready 1 min; cron 14:00 e 22:00 America/Sao_Paulo.

## IA existente vs gap WhatsApp-AI
- **PIX OCR / auto-aprovação**: `emergentintegrations` + `EMERGENT_LLM_KEY` + modelo openai/gpt-4o no fluxo de comprovante de pedido (server.py).
- **Ausente:** assistente WhatsApp inbound, tool-calling financeiro seguro, `OPENAI_API_KEY` dedicado no fluxo Baileys, outbox/idempotência de fechamento, allowlist rígida de grupo único.

## Auth / domínio de negócio (resumo)
- **Gestor:** HTTP Basic; senha de env `GESTOR_PASSWORD` (há default no código — ver scan); tenants SHA-256 sem salt adequado.
- **Prazo / caixa / estoque:** implementados no monólito + routers; `ganoh/staged-audit` já avançou idempotência financeira (não mergeado).
- **Staff gate:** senha fixa no frontend (`StaffAccessPage.js`) — não é auth de API.

## Scan de segurança (SEM valores de segredo)
Achados por **caminho / variável / padrão** (valores omitidos de propósito):

1. **CRÍTICO — defaults literais de provedor WhatsApp** em `backend/server.py` e `backend/green_api.py`: variáveis `GREEN_API_TOKEN`, `GREEN_API_INSTANCE`, além de URLs default Green API. Tratar como **expostos**; planejar rotação e remoção de defaults.
2. **ALTO — JIDs de grupo WhatsApp com default literal** em `backend/server.py`: `WHATSAPP_GROUP_ID`, `WHATSAPP_GROUP_RUNNER`.
3. **ALTO — default de `GESTOR_PASSWORD` / criação de tenant** em `backend/server.py` (env com fallback string).
4. **ALTO — senha staff hardcoded** em `frontend/src/pages/StaffAccessPage.js` (`STAFF_PASSWORD`).
5. **MÉDIO — PRD histórico** `memory/PRD.md` menciona senha de gestor em texto (documento legado).
6. **MÉDIO — credenciais Basic em localStorage (base64)** no Gestor (não é criptografia).
7. **MÉDIO — erros HTTPX** podem vazar URL com token Green API em logs/respostas se provider greenapi.
8. **Positivo:** Baileys usa env obrigatório para `WHATSAPP_INTERNAL_TOKEN` / `WHATSAPP_SESSION_KEY` (≥32); bind loopback; `timingSafeEqual`; sessão cifrada; render.yaml usa `generateValue` / `sync:false` para segredos.

**Ação recomendada (ETAPA 3+):** rotacionar tokens Green API e senhas com default; remover literais do código; garantir que produção não depende de Green API se o caminho for só Baileys.

## Diff estratégico das branches (read-only)
### ganoh/continuity-sync
- Script `scripts/sync_from_emergent.py` (dry-run default, upsert-only, sem delete).
- Workflow GitHub hourly (ainda fora de main → inativo).
- Bloqueio declarado: conectividade Mongo destino / credenciais.
- Não altera WhatsApp/Baileys.

### ganoh/staged-audit
- Hardening financeiro (prazo settlement, PIX idempotency, testes).
- Documentação extensa de riscos de caixa, rotas duplicadas, WhatsApp gaps.
- **Não mergear** até gates financeiros + validação autenticada.

### ganoh/whatsapp-ai
- Aponta para o mesmo commit de main — **placeholder vazio**; trabalho WhatsApp AI ainda não começou nessa branch.

## Lacunas vs requisitos típicos WhatsApp AI / operação
1. Sem inbound (`messages.upsert`) → sem bot/comprovante por chat.
2. Envio e Baileys desligados sob migração (`MIGRATION_PENDING` / `WHATSAPP_SEND_ENABLED`).
3. Relatórios 14h/22h existem no código mas scheduler off; sem outbox/idempotência data+turno+loja.
4. `WHATSAPP_SEND_ENABLED` não cobre todos os caminhos Green API do backend.
5. Free Render hiberna → sessão Baileys não fica online contínua.
6. Correções financeiras e sync de continuidade ainda isolados em outras branches.
7. Produção UI estática ainda pode apontar para legacy Emergent (documentado nas outras branches) — **não validar migração como concluída**.

## Riscos (para ETAPA 3)
- Ativar envio ou scheduler antes de dados validados → mensagens/lançamentos espúrios.
- Rotacionar `WHATSAPP_SESSION_KEY` sem migração → invalida sessão cifrada.
- Merge precoce de staged-audit/continuity sem testes/gates.
- Usar Green API com token default no código.
- Implementar AI inbound sem ledger/idempotência/allowlist.

## Próximos passos (ETAPA 3 sugerida)
1. Trabalhar **somente** em `ganoh/grok-whatsapp-ai`.
2. Desenhar inbound Baileys (`messages.upsert`) + fila/outbox, sem ligar `WHATSAPP_SEND_ENABLED` em prod.
3. Remover/neutralizar defaults de segredo no código (PR dedicado, sem expor valores).
4. Reaproveitar UI WhatsAppTab; não reinventar QR/status.
5. Coordenar com continuity-sync (Mongo destino) e staged-audit (idempotência) antes de qualquer enable de flags.
6. Testes locais Node/Python sem Mongo de produção e sem envio real.

## Commits desta branch
- Nenhum commit remoto: ETAPA 2 falhou com 403 no GitHub MCP (integration sem permissão de escrita em refs/contents).
- Artefato local: `/workspace/Ganoh1/GANOH_GROK_PROGRESS.md` (pronto para commit quando o token/App tiver Contents:write + criação de branch).
- Próxima ação operacional: conceder write ao MCP GitHub (ou PAT com `contents:write` + `workflows` se necessário) e reexecutar create_branch + create_or_update_file **somente** em `ganoh/grok-whatsapp-ai`.

