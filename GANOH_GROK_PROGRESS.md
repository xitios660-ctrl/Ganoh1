# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 6 — AI WhatsApp (OpenAI seguro): CONCLUÍDA** em 24/09/2026 ~02:55 BRT (America/Sao_Paulo), branch local `ganoh/grok-whatsapp-ai` only.  
**ETAPA 5 — Gestor QR/status UI:** concluída.  
**ETAPA 4 — Baileys inbound:** concluída.  
**ETAPA 3 — Security hardening:** concluída.  
**ETAPA 2 — Branch remota:** ainda BLOQUEADA — MCP GitHub write **403** (Contents:write). Sem push / sem criar branch remota. Sem merge / sem deploy.

Regras respeitadas: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`); flags `MIGRATION_PENDING` / `SCHEDULER_ENABLED` / `WHATSAPP_SEND_ENABLED` intactas em `render.yaml`. Sem Meta Cloud API. Sem inventar números financeiros (stub ETAPA 7). Sem keys em código/logs/commits.

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
| ganoh/grok-whatsapp-ai | **local** — ETAPA 1/3/4/5/6; **remoto inexistente** (403) |

## Env vars (nomes apenas — nunca gravar valores)
| Nome | Uso |
| --- | --- |
| `OPENAI_API_KEY` | Obrigatória para respostas WhatsApp AI |
| `OPENAI_MODEL` | Opcional; default `gpt-4o-mini` |
| `EMERGENT_LLM_KEY` | Fallback só para `is_configured()` / `aiStatus=pending` (path AI WhatsApp prefere OPENAI) |
| `WHATSAPP_SEND_ENABLED` | Se não `true`, IA calcula resposta mas **não envia** (`would_reply`) |

## ETAPA 6 — AI WhatsApp (esta sessão)

### Comportamento
1. Módulo `backend/whatsapp_ai.py`: `is_configured()`, `is_openai_ready()`, `get_ai_status()`, `chat_reply()` / `achat_reply()`.
2. Chaves só via env; nunca logadas. Completer injetável para testes.
3. System prompt: assistente GANOH; nunca inventar números; ações sensíveis exigem Gestor.
4. Stub financeiro (sem DB / ETAPA 7) e stub de mutações sensíveis — **sem** chamar OpenAI nesses casos.
5. Webhook `POST /api/whatsapp/inbound`: após persistir, para texto 1:1, se OPENAI pronto → gera reply; se `WHATSAPP_SEND_ENABLED!=true` → `aiStatus=would_reply` (não envia).
6. Grupos / não-texto: skip. AI indisponível: `unavailable` sem crash.
7. `GET /api/whatsapp/status`: `aiConfigured` + `aiStatus` (`active`|`pending`|`unavailable`).
8. Gestor `WhatsAppTab`: `aiStatus===active` → **IA ativa**; senão **Configuração pendente**.

### Arquivos
| Arquivo | Mudança |
| --- | --- |
| `backend/whatsapp_ai.py` | **novo** — integração OpenAI segura |
| `backend/server.py` | inbound AI draft + status `aiStatus` |
| `frontend/src/components/gestor/WhatsAppTab.js` | UI IA ativa / pendente |
| `frontend/src/pages/GestorPage.js` | prop/state `aiStatus` |
| `whatsapp/inbound.mjs` | comentários (AI no backend) |
| `backend/tests/test_whatsapp_ai.py` | **novo** unit tests |
| `backend/tests/test_whatsapp_inbound_ai_path.py` | **novo** path gating tests |
| `GANOH_GROK_PROGRESS.md` | este doc |

### Testes
- `python3 -m py_compile` `backend/whatsapp_ai.py` + `backend/server.py`: OK
- `node --check` WhatsAppTab / GestorPage / inbound.mjs: OK
- pytest (venv) `test_whatsapp_ai.py` + `test_whatsapp_inbound_ai_path.py`: **17 passed**
- Sem chamada real OpenAI / Mongo / deploy
- `frontend` `npm run build`: **não** executado (`node_modules` ausente)

### Riscos / limitações
- Envio real continua bloqueado por `WHATSAPP_SEND_ENABLED=false` (correto).
- Consultas financeiras reais = ETAPA 7 (stub atual).
- Push remoto ainda 403.
- Credenciais historicamente hardcoded (ETAPA 3) ainda precisam rotação no provedor.
- `aiReplyDraft` gravado no inbound doc; listagens Gestor **não** projetam corpo/draft.

### Não alterado (de propósito)
- `render.yaml` flags de manutenção
- Branches reservadas / main
- Sem push / merge / deploy
- Sem Meta Cloud API; Baileys only
- Sem ETAPA 7 DB financeiro / 8 comprovantes / 9 reports / Charts sync

### Commits locais nesta branch (ETAPA 6)
| SHA | Mensagem |
| --- | --- |
| (ver `git log`) | feat: secure OpenAI WhatsApp AI module + wire |
| (ver `git log`) | docs: ETAPA 6 progress in GANOH_GROK_PROGRESS.md |

## Próxima etapa
**ETAPA 7 — Consultas financeiras via Mongo** (tools/DB reais para a IA; ainda sem inventar números; confirmação Gestor para mutações), sem ligar send / sem deploy, só em `ganoh/grok-whatsapp-ai`.

## Bloqueio operacional persistente
MCP `user-GitHub-xai` / Contents:write → **403**. Não tentar push/create remote branch até o usuário conceder permissão. Artefatos ficam locais em `/workspace/Ganoh1`.
