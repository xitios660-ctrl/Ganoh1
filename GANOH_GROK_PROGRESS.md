# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 5 — Gestor QR/status UI: CONCLUÍDA** em 24/09/2026 ~01:50 BRT (America/Sao_Paulo), branch local `ganoh/grok-whatsapp-ai` only.  
**ETAPA 4 — Baileys inbound:** concluída (commits anteriores).  
**ETAPA 3 — Security hardening:** concluída.  
**ETAPA 2 — Branch remota:** ainda BLOQUEADA — MCP GitHub write **403** (Contents:write). Sem push / sem criar branch remota. Sem merge / sem deploy.

Regras respeitadas: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`); flags `MIGRATION_PENDING` / `SCHEDULER_ENABLED` / `WHATSAPP_SEND_ENABLED` intactas em `render.yaml`. Sem auto-reply / sem AI (ETAPA 6). Sem download de comprovante (ETAPA 8). Sem hard-code de secrets.

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
| ganoh/grok-whatsapp-ai | **local** — ETAPA 1/3/4/5; **remoto inexistente** (403) |

## ETAPA 5 — Gestor QR/status UI (esta sessão)

### Comportamento
1. `WhatsAppTab` no painel Gestor exibe estados PT-BR com indicadores distintos: `connected`, `disconnected`, `connecting`, `waiting_qr`, `reconnecting`, `logged_out`, `connection_conflict`, `offline`.
2. Sem sessão válida: CTAs **Conectar WhatsApp** / **Gerar QR Code** (disparam `POST /api/whatsapp/connect`).
3. QR renderizado **dentro** da aba, centralizado, `max-w-[240px]` responsivo; some quando `connected`.
4. Conectado: banner “WhatsApp conectado” + “Sessão protegida e persistente”; UI respeita status (não força QR se sessão persistida).
5. **Grupo de relatórios**: link de convite / seleção na lista / salvar destino (callbacks existentes).
6. **IA**: placeholder somente — “configuração pendente” ou sinal `aiConfigured` (presença de chave LLM, sem expor valor). Sem OpenAI / sem auto-reply.
7. **Relatórios automáticos**: informativo `14:00 / 22:00` (America/Sao_Paulo); scheduler **não** ligado.
8. Última conexão / último relatório / erros recentes: campos seguros do status API (sem secrets).
9. Backend `GET /api/whatsapp/status` enriquecido (read-mostly): `lastConnectedAt`, `lastReportAt`, `recentErrors`, `aiConfigured`, `reportSchedule`, `currentTarget`; erros sanitizados.
10. Baileys `/getStateInstance` expõe `lastConnectedAt` + `recentErrors` (mensagens curtas filtradas).

### Arquivos
| Arquivo | Mudança |
| --- | --- |
| `frontend/src/components/gestor/WhatsAppTab.js` | layout profissional status/QR/grupos/IA/relatórios/erros |
| `frontend/src/pages/GestorPage.js` | estados extras + props; poll 5s inalterado |
| `backend/server.py` | status enriquecido + sanitização de erros QR/groups/status |
| `whatsapp/server.mjs` | `lastConnectedAt` / `recentErrors` no status Baileys |

### Testes
- `node --check` em `whatsapp/server.mjs`, `WhatsAppTab.js`, `GestorPage.js`: OK
- `python3 -m py_compile` + AST parse em `backend/server.py`: OK
- `frontend` `npm run build`: **não** executado (`node_modules` ausente no box)
- WhatsApp live / Mongo live / Render deploy: **não** executados

### Riscos / limitações
- `lastReportAt` só aparece se existir `settings.whatsapp_last_report_at` (ainda não gravado pelos jobs — UI mostra “—”).
- `aiConfigured` é só presença de env LLM; ETAPA 6 implementa a IA de fato.
- Push remoto ainda 403; trabalho só local.
- Credenciais historicamente hardcoded (ETAPA 3) ainda precisam rotação no provedor.
- Sem `npm run build` visual regression não validada no box.

### Não alterado (de propósito)
- `render.yaml` flags de manutenção
- Branches reservadas / main
- Sem push / merge / deploy
- Sem ligar `WHATSAPP_SEND_ENABLED` / scheduler / migration
- Sem Meta Cloud API; Baileys only
- Sem OpenAI / auto AI replies / comprovantes / Charts sync

### Commits locais nesta branch (ETAPA 5)
| SHA | Mensagem |
| --- | --- |
| `363ff56` | feat: Gestor WhatsApp QR/status UI |
| tip docs | `GANOH_GROK_PROGRESS.md` ETAPA 5 — ver `git log -1` na branch |
| (prévio) `c7403de` | docs: ETAPA 4 Baileys inbound progress |

## Próxima etapa
**ETAPA 6 — AI WhatsApp** (integração OpenAI / respostas no fluxo Baileys), sem ligar send / sem deploy, só em `ganoh/grok-whatsapp-ai`.

## Bloqueio operacional persistente
MCP `user-GitHub-xai` / Contents:write → **403**. Não tentar push/create remote branch até o usuário conceder permissão. Artefatos ficam locais em `/workspace/Ganoh1`.
