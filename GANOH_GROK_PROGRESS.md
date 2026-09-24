# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 4 — Baileys inbound (`messages.upsert` + persist + webhook): CONCLUÍDA** em 24/09/2026 ~00:50 BRT (America/Sao_Paulo), branch local `ganoh/grok-whatsapp-ai` only.  
**ETAPA 2 — Branch remota:** ainda BLOQUEADA — MCP GitHub write **403** (Contents:write). Sem push / sem criar branch remota. Sem merge / sem deploy.  
**ETAPA 3 — Security hardening:** concluída (commits anteriores nesta branch).

Regras respeitadas: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`); flags `MIGRATION_PENDING` / `SCHEDULER_ENABLED` / `WHATSAPP_SEND_ENABLED` intactas em `render.yaml`. Sem auto-reply / sem AI (ETAPA 6/7). Sem download de comprovante (ETAPA 8).

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
| ganoh/grok-whatsapp-ai | **local** — ETAPA 1/3/4; **remoto inexistente** (403) |

## ETAPA 4 — Baileys inbound (esta sessão)

### Comportamento
1. `whatsapp/server.mjs` escuta `messages.upsert` (somente `type === 'notify'` — ignora flood de histórico `append`).
2. Ignora `fromMe`, `status@broadcast`, mensagens sem id/jid.
3. Dedup atômico em Mongo `baileys_processed_messages` (`_id` = messageId) com TTL ~7 dias (`expiresAt` + índice TTL).
4. Concorrência: mapa in-flight por messageId (mesma Promise) + claim unique no Mongo.
5. Persiste evento seguro em `baileys_inbound` (texto truncado, metadados de mídia; **sem** baixar mídia / sem confiar conteúdo financeiro).
6. Notifica backend via HTTP loopback `POST /api/whatsapp/inbound` com header `x-whatsapp-token` (`WHATSAPP_INTERNAL_TOKEN`). Se backend cair, outbound fica com `backendNotified=false` (reprocessável depois).
7. Backend grava idempotente em `whatsapp_inbound` (`$setOnInsert` por messageId). **Sem** mutações financeiras, sem AI, sem auto-reply.
8. `WHATSAPP_SEND_ENABLED` continua gating só de envio; inbound funciona com send desligado.
9. Em `loggedOut`/`badSession`: continua apagando **apenas** `baileys_auth` (nunca dados financeiros / inbound).
10. Logger Baileys permanece `silent`; erros só com `code`/`name` seguros.

### Arquivos
| Arquivo | Mudança |
| --- | --- |
| `whatsapp/inbound.mjs` | **novo** — normalize / dedup / persist / notify |
| `whatsapp/inbound.test.mjs` | **novo** — unit tests sem Mongo/WhatsApp live |
| `whatsapp/server.mjs` | wire `messages.upsert` + indexes + `GET /inbound/recent` |
| `backend/server.py` | `verify_baileys_internal_token`, `POST/GET /api/whatsapp/inbound`, indexes |

### Endpoints novos
| Método | Path | Auth | Função |
| --- | --- | --- | --- |
| POST | `/api/whatsapp/inbound` | `x-whatsapp-token` | webhook Baileys → Mongo `whatsapp_inbound` |
| GET | `/api/whatsapp/inbound` | gestor/manager basic | listagem metadados (sem bodies) |
| GET | Baileys `/inbound/recent` | `x-whatsapp-token` | peek sidecar (sem bodies) |

### Testes
- `node --check` em `whatsapp/inbound.mjs`, `whatsapp/server.mjs`: OK
- `node --test whatsapp/inbound.test.mjs whatsapp/auth.test.mjs`: **9/9 pass**
- `python3 -m py_compile backend/server.py` + AST parse: OK
- Import completo FastAPI/pytest / Mongo live / WhatsApp live: **não** executados (sem deps de produção no box)

### Riscos / limitações
- Notificação backend é best-effort (1 tentativa); sem worker de retry ainda — docs/outbox flag `backendNotified` cobre recuperação futura.
- Texto inbound é persistido (truncado) para ETAPA 6/7; listagens HTTP omitem bodies, mas a collection contém texto — acesso Mongo = dados sensíveis de cliente.
- Stub `comprovanteStub` só marca candidato; download/OCR/aprovação = ETAPA 8.
- Push remoto ainda 403; trabalho só local.
- Credenciais historicamente hardcoded (ETAPA 3) ainda precisam rotação no provedor.

### Não alterado (de propósito)
- `render.yaml` flags de manutenção
- Branches reservadas / main
- Sem push / merge / deploy
- Sem ligar `WHATSAPP_SEND_ENABLED` / scheduler / migration
- Sem Meta Cloud API; Baileys only
- Sem auto AI replies

### Commits locais nesta branch (ETAPA 4)
| SHA | Mensagem |
| --- | --- |
| (prévio) `39d3a13` | docs: add GANOH_GROK_PROGRESS.md (etapa 1 audit) |
| (prévio) `c6bc3cb` | security: remove hard-coded WhatsApp/gestor/prazo defaults |
| (prévio) `b79f251` / `e01d5da` | docs ETAPA 3 |
| `7d4b481` | feat: Baileys inbound reception + backend webhook |
| tip docs | `GANOH_GROK_PROGRESS.md` ETAPA 4 — ver `git log -1` na branch |

## Próxima etapa
**ETAPA 5 — Gestor QR/status UI** (painel gestor para QR/conexão/status Baileys), sem ligar send / sem deploy. Continuar só em `ganoh/grok-whatsapp-ai`.

## Bloqueio operacional persistente
MCP `user-GitHub-xai` / Contents:write → **403**. Não tentar push/create remote branch até o usuário conceder permissão. Artefatos ficam locais em `/workspace/Ganoh1`.
