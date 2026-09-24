# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 7 — Consultas financeiras Mongo (WhatsApp AI): CONCLUÍDA** em 24/09/2026 ~04:00 BRT (America/Sao_Paulo), branch local `ganoh/grok-whatsapp-ai` only.  
**ETAPA 6 — AI WhatsApp (OpenAI seguro):** concluída.  
**ETAPA 5 — Gestor QR/status UI:** concluída.  
**ETAPA 4 — Baileys inbound:** concluída.  
**ETAPA 3 — Security hardening:** concluída.  
**ETAPA 2 — Branch remota:** ainda BLOQUEADA — MCP GitHub write **403** (Contents:write). Sem push / sem criar branch remota. Sem merge / sem deploy.

Regras respeitadas: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`); flags `MIGRATION_PENDING` / `SCHEDULER_ENABLED` / `WHATSAPP_SEND_ENABLED` intactas em `render.yaml`. Sem Meta Cloud API. Sem inventar números financeiros (fatos oficiais do Mongo ou “sem dados”). Sem keys/MONGO_URL em código/logs/commits.

## Referências
| Item | Valor |
| --- | --- |
| Repo | xitios660-ctrl/Ganoh1 |
| Produção UI | https://ganoh.onrender.com |
| Legacy (read-only) | https://charts-3.emergent.host |
| main SHA auditado | `6805956bfd3f41b385928151c115f3d4d3c7afc1` |
| Clone local | `/workspace/Ganoh1` |
| Branch de trabalho | `ganoh/grok-whatsapp-ai` (local only) |

## Branches
| Branch | Estado |
| --- | --- |
| main | intocado |
| ganoh/whatsapp-ai | intocado |
| ganoh/continuity-sync | intocado |
| ganoh/staged-audit | intocado |
| ganoh/grok-whatsapp-ai | **local** — ETAPA 1/3/4/5/6/7; **remoto inexistente** (403) |

## Env vars (nomes apenas — nunca gravar valores)
| Nome | Uso |
| --- | --- |
| `OPENAI_API_KEY` | Obrigatória para respostas WhatsApp AI |
| `OPENAI_MODEL` | Opcional; default `gpt-4o-mini` |
| `EMERGENT_LLM_KEY` | Fallback só para `is_configured()` / `aiStatus=pending` (path AI WhatsApp prefere OPENAI) |
| `WHATSAPP_SEND_ENABLED` | Se não `true`, IA calcula resposta mas **não envia** (`would_reply`) |
| `MONGO_URL` / `DB_NAME` | Backend; AI finance usa `whatsapp_finance.set_db(db)` — sem ler URL no módulo AI |

## ETAPA 7 — Consultas financeiras (esta sessão)

### Decisão de desenho
**Intent detect + fetch Mongo read-only + fatos no prompt** (não OpenAI function-calling). Motivo: mais simples, 100% testável com FakeDB, sem schema de tools, alinhado ao stub ETAPA 6.

### Fluxo
1. Inbound 1:1 texto → `achat_reply`.
2. Sensível (apagar/zerar/confirmar PIX/saque/…) → stub Gestor; **sem** DB mutate; **sem** OpenAI.
3. Financeiro → `whatsapp_finance.fetch_facts_for_text` (collections `orders`, `pix_adjustments`, `prazo_*`, `cash_*`, `stock`).
4. Fatos oficiais injetados no system prompt → OpenAI **só formata/explica**.
5. Sem dados / falha de consulta → mensagem explícita; **nunca inventa números**.
6. `WHATSAPP_SEND_ENABLED!=true` → `would_reply` (inalterado).

### Intents cobertos
| Intent | Exemplos |
| --- | --- |
| `sales_today` / `sales_by_store` | quanto vendeu hoje; por loja Runner / GYM Londres |
| `pix_today` / `cash_today` | PIX; dinheiro |
| `debts_list` / `debt_customer` | quem está devendo; quanto X deve |
| `prazo_payments_today` | pagamentos de prazo hoje |
| `morning_close` | fechamento da manhã (06:00–14:00 BRT) |
| `cash_drawer` | saldo/diferença no caixa (saldo **esperado** sistema; física = Gestor) |
| `low_stock` | estoque baixo |
| `day_summary` | resumo do dia |

Timezone “hoje” / turnos: **America/Sao_Paulo** (mesmo critério de `get_today_cash`).

### Arquivos
| Arquivo | Mudança |
| --- | --- |
| `backend/whatsapp_finance.py` | **novo** — intents + queries read-only + `FinanceFacts` |
| `backend/whatsapp_ai.py` | remove stub cego ETAPA 7; injeta fatos; `achat_reply` busca DB |
| `backend/server.py` | `whatsapp_finance.set_db(db)`; docstring inbound |
| `backend/tests/test_whatsapp_finance.py` | **novo** — FakeDB / mocks |
| `backend/tests/test_whatsapp_ai.py` | ajuste path financeiro sem fatos |
| `backend/tests/test_whatsapp_inbound_ai_path.py` | ajuste mirror sync |
| `GANOH_GROK_PROGRESS.md` | este doc |

### Testes
- `python3 -m py_compile` `whatsapp_ai.py` + `whatsapp_finance.py`; AST `server.py`: OK
- pytest (venv `/tmp/ganoh-venv`) `test_whatsapp_finance.py` + `test_whatsapp_ai.py` + `test_whatsapp_inbound_ai_path.py`: **30 passed**
- Sem conexão Mongo produção; sem mutação financeira; sem OpenAI real; sem deploy
- `render.yaml` travas intactas (`MIGRATION_PENDING=true`, `SCHEDULER_ENABLED=false`, `WHATSAPP_SEND_ENABLED=false`)
- `frontend` `npm run build`: **não** executado (`node_modules` ausente)

### Riscos / limitações
- Envio real continua bloqueado por `WHATSAPP_SEND_ENABLED=false` (correto).
- “Diferença no caixa” = saldo esperado do sistema; contagem física continua Gestor.
- Breakdown por **vendedor** individual não existe no schema — responde por **loja**.
- FakeDB cobre queries usadas; edge cases de offsets mistos herdados do backend.
- Push remoto ainda 403.
- Credenciais historicamente hardcoded (ETAPA 3) ainda precisam rotação no provedor.

### Não alterado (de propósito)
- `render.yaml` flags de manutenção
- Branches reservadas / main
- Sem push / merge / deploy
- Sem UPSERT/DELETE financeiro
- Sem Meta Cloud API; Baileys only
- Sem ETAPA 8 comprovantes / 9 reports / Charts sync

### Commits locais nesta branch (ETAPA 7)
| SHA | Mensagem |
| --- | --- |
| (ver `git log`) | feat: Mongo finance tools for WhatsApp AI |
| (ver `git log`) | docs: ETAPA 7 progress |

## Próxima etapa
**ETAPA 8 — Comprovantes** (interpretação/anexo de comprovantes no WhatsApp AI), sem ligar send / sem deploy, só em `ganoh/grok-whatsapp-ai`.

## Bloqueio operacional persistente
MCP GitHub Contents:write → **403**. Não tentar push/create remote branch até o usuário conceder permissão. Artefatos ficam locais em `/workspace/Ganoh1`.
