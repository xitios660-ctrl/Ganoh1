# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 8 — Comprovantes via WhatsApp Baileys: CONCLUÍDA** em 24/09/2026 ~05:10 BRT (America/Sao_Paulo), branch local `ganoh/grok-whatsapp-ai` only.  
**ETAPA 7 — Consultas financeiras Mongo:** concluída.  
**ETAPA 6 — AI WhatsApp (OpenAI seguro):** concluída.  
**ETAPA 5 — Gestor QR/status UI:** concluída.  
**ETAPA 4 — Baileys inbound:** concluída.  
**ETAPA 3 — Security hardening:** concluída.  
**ETAPA 2 — Branch remota:** ainda BLOQUEADA — MCP GitHub write **403** (Contents:write). Sem push / sem criar branch remota. Sem merge / sem deploy.

Regras respeitadas: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`); flags `MIGRATION_PENDING` / `SCHEDULER_ENABLED` / `WHATSAPP_SEND_ENABLED` intactas em `render.yaml`. Sem Meta Cloud API. Sem inventar números financeiros. Sem keys/MONGO_URL em código/logs/commits. Comprovantes **nunca** auto-confirmam pagamento.

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
| ganoh/grok-whatsapp-ai | **local** — ETAPA 1/3/4/5/6/7/8; **remoto inexistente** (403) |

## Env vars (nomes apenas — nunca gravar valores)
| Nome | Uso |
| --- | --- |
| `OPENAI_API_KEY` | Obrigatória para respostas WhatsApp AI / OCR comprovante |
| `OPENAI_MODEL` | Opcional; default `gpt-4o-mini` |
| `EMERGENT_LLM_KEY` | Fallback só para `is_configured()` / `aiStatus=pending` (path AI WhatsApp prefere OPENAI) |
| `WHATSAPP_SEND_ENABLED` | Se não `true`, IA/ack calcula resposta mas **não envia** (`would_reply`) |
| `WHATSAPP_INTERNAL_TOKEN` | Auth sidecar Baileys → backend (`/inbound`, `/inbound/media`) |
| `MONGO_URL` / `DB_NAME` | Backend; módulos usam `set_db(db)` — sem ler URL no módulo |

## ETAPA 8 — Comprovantes (esta sessão)

### Decisão de desenho
**Pending review + Gestor confirm/correct/refuse** — sem auto-mutação financeira.  
No confirm: grava revisão + audit (`origin=WhatsApp / comprovante`); **não** chama APIs de PIX/prazo/caixa (caminho incompleto mais seguro). Gestor aplica dinheiro pelos fluxos existentes.

### Fluxo
1. Cliente envia imagem → Baileys `normalizeInbound` marca `comprovanteStub`.
2. Sidecar notifica `POST /api/whatsapp/inbound` → backend cria pending (`awaiting_media`).
3. Sidecar baixa mídia (Baileys `downloadMediaMessage`) e envia `POST /api/whatsapp/inbound/media` (base64, ≤2 MiB, jpeg/png/webp).
4. Backend armazena binary em `whatsapp_comprovante_media` (Mongo), OCR opcional (OpenAI vision), match read-only (orders/prazo), status `awaiting_gestor`.
5. Gestor UI: lista + Confirmar / Corrigir / Recusar.
6. PDF/document: metadata only — **images only** para OCR (PDF adiado).
7. `WHATSAPP_SEND_ENABLED!=true` → ack `would_reply` (sem send).

### Status
| Status | Significado |
| --- | --- |
| `awaiting_media` | Candidate sem binary ainda |
| `awaiting_gestor` | Pronto para revisão (default após doubt/extração) |
| `confirmed` / `corrected` | Revisão Gestor (sem money apply automático) |
| `refused` | Recusado pelo Gestor |

### Arquivos
| Arquivo | Mudança |
| --- | --- |
| `backend/whatsapp_comprovantes.py` | **novo** — pending, media, extract, match, confirm/refuse, audit |
| `backend/server.py` | inbound cria pending; `/inbound/media`; rotas Gestor `/whatsapp/comprovantes*` |
| `backend/whatsapp_ai.py` | prompt: comprovantes = fluxo Gestor (não “etapa futura”); `MSG_COMPROVANTE_PENDING` |
| `whatsapp/inbound.mjs` | `notifyBackendMedia` + download hook no pipeline |
| `whatsapp/server.mjs` | `downloadMediaMessage` para imagens comprovante |
| `frontend/.../WhatsAppTab.js` | seção Comprovantes (lista + ações) |
| `backend/tests/test_whatsapp_comprovantes.py` | **novo** — FakeDB |
| `backend/tests/test_whatsapp_inbound_ai_path.py` | media skip AI + prompt |
| `whatsapp/inbound.test.mjs` | media upload / mime / size |
| `GANOH_GROK_PROGRESS.md` | este doc |

### Testes
- `python3 -m py_compile` `whatsapp_comprovantes.py` + `whatsapp_ai.py`; AST `server.py`: OK
- `node --check` WhatsAppTab / inbound / server.mjs: OK
- pytest (venv `/tmp/ganoh-venv`) comprovantes + ai + finance + inbound path: **40 passed**
- node `--test` `whatsapp/inbound.test.mjs`: **11 passed**
- Sem Mongo produção; sem OpenAI real; sem send; sem deploy
- `render.yaml` travas intactas
- `frontend` `npm run build`: **não** executado (`node_modules` ausente)

### Riscos / limitações
- Confirm **não** aplica dinheiro automaticamente — Gestor usa PIX/prazo UI existente.
- PDF não suportado no OCR/download (só imagens jpeg/png/webp).
- Retention de binary Mongo: nota no record; política de purge TBD (nunca apagar audit financeiro).
- Envio real bloqueado por `WHATSAPP_SEND_ENABLED=false` (correto).
- Push remoto ainda 403.
- Credenciais historicamente hardcoded (ETAPA 3) ainda precisam rotação no provedor.

### Não alterado (de propósito)
- `render.yaml` flags de manutenção
- Branches reservadas / main
- Sem push / merge / deploy
- Sem UPSERT/DELETE financeiro em orders/prazo/cash/pix via WhatsApp
- Sem Meta Cloud API; Baileys only
- Sem ETAPA 9 reports / Charts sync

## Próxima
**ETAPA 9** — relatórios / agendamento (respeitando `SCHEDULER_ENABLED=false` até liberação).
