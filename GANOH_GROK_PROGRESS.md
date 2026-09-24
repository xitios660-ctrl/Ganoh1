# GANOH — Progresso Grok (WhatsApp AI)

## Etapa atual
**ETAPA 3 — Security hardening (defaults removidos): CONCLUÍDA** em 24/09/2026 ~00:20 BRT (America/Sao_Paulo), branch local `ganoh/grok-whatsapp-ai` only.  
**ETAPA 2 — Branch remota:** ainda BLOQUEADA — MCP GitHub write **403** (Contents:write). Sem push / sem criar branch remota. Sem merge / sem deploy.

Regras respeitadas: sem push/deploy/merge em produção; sem alterar branches reservadas (`main`, `ganoh/continuity-sync`, `ganoh/staged-audit`, `ganoh/whatsapp-ai`); flags `MIGRATION_PENDING` / `SCHEDULER_ENABLED` / `WHATSAPP_SEND_ENABLED` intactas em `render.yaml`.

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
| ganoh/grok-whatsapp-ai | **local** — commits de progresso + security; **remoto inexistente** (403) |

## ETAPA 1 — Auditoria (resumo)
Ver seções anteriores / histórico: Baileys sem inbound; Green API legado; flags de manutenção; gaps AI. Auditoria concluída em 23/09/2026.

## ETAPA 3 — Security hardening (esta sessão)

### O que foi neutralizado (caminhos / nomes de variável — SEM valores)
1. `backend/server.py`: `GREEN_API_URL`, `GREEN_API_INSTANCE`, `GREEN_API_TOKEN` — sem default literal; `get_green_api_url` falha fechado se incompleto.
2. `backend/server.py`: `WHATSAPP_GROUP_ID`, `WHATSAPP_GROUP_RUNNER` — default vazio (sem JID hardcoded); `send_whatsapp_message` recusa target vazio.
3. `backend/server.py`: `GESTOR_PASSWORD` — sem default; `verify_gestor` → 503 se ausente; `ensure_default_tenant` não cria/sync sem env.
4. `backend/server.py`: `PRAZO_PASSWORD`, `CLEAR_DATA_PASSWORD` — sem default; helpers `_require_*` falham fechado se env vazio.
5. `backend/green_api.py`: mesmos `GREEN_API_*` + fail-closed em `get_api_url`.
6. `backend/routers/whatsapp.py`: `GREEN_API_URL` sem default de host; fail-closed URL builder.
7. `backend/routers/auth.py`: `GESTOR_PASSWORD` sem default (`admin123` removido); 503 se ausente.
8. `backend/routers/prazo.py`: default módulo `PRAZO_PASSWORD` vazio + `_require_prazo_password`.
9. `backend/sync_from_reference.py`: `GESTOR_PASSWORD` sem default.
10. `frontend/src/pages/StaffAccessPage.js`: `STAFF_PASSWORD` via `REACT_APP_STAFF_PASSWORD` (vazio = acesso bloqueado).
11. `memory/PRD.md`: redação de menções históricas de senha.
12. `backend/tests/*`: literais de senha/JID de produção substituídos por placeholder de teste / mensagens sem JID.

### Rotação obrigatória (valores NÃO repetidos aqui)
Credenciais que **já estiveram hardcoded** no repo devem ser consideradas **expostas** e rotacionadas no provedor / Render / Mongo tenants, incluindo:
- Green API token + instance (se ainda existirem em algum painel)
- `GESTOR_PASSWORD` / hash do tenant gestor
- Senha staff (`REACT_APP_STAFF_PASSWORD`)
- `PRAZO_PASSWORD`, `CLEAR_DATA_PASSWORD`
- JIDs de grupo (reconfigurar via env / UI set-target; não reintroduzir no código)

### Arquivos alterados (commit security)
- `backend/server.py`, `backend/green_api.py`
- `backend/routers/auth.py`, `backend/routers/prazo.py`, `backend/routers/whatsapp.py`
- `backend/sync_from_reference.py`
- `frontend/src/pages/StaffAccessPage.js`
- `memory/PRD.md`
- vários `backend/tests/test_*.py` (redação de fixtures)

### Não alterado (de propósito)
- `render.yaml` flags de manutenção
- Branches reservadas / main
- Sem push remoto
- Módulos Green API mantidos (referenciados) mas defaults neutralizados
- Sem implementação de inbound Baileys (ETAPA 4)

### Testes
- `python3 -m py_compile` / AST parse nos módulos Python alterados: OK
- `node --check frontend/src/pages/StaffAccessPage.js`: OK
- Asserts locais fail-closed (Green API URL builder + empty password reject): OK
- Import completo `server.py` / pytest: **não** executados (deps httpx/fastapi ausentes no box; sem Mongo de produção)
- `backend/tests/test_render_deployment.py` ainda define env de teste antes do import — compatível com fail-closed

### Riscos remanescentes
- Frontend staff gate ainda é client-side (mesmo com env): não é auth de API.
- Produção Render precisa ter `GESTOR_PASSWORD`, `PRAZO_PASSWORD`, `CLEAR_DATA_PASSWORD`, groups JIDs e (se greenapi) credenciais **já** no painel; senão login/prazo quebram ao sair de `MIGRATION_PENDING` — esperado (fail closed).
- `REACT_APP_STAFF_PASSWORD` entra no bundle no build; preferir gate server-side depois.
- Histórico git ainda contém literais antigos → rotação continua necessária.
- Push remoto bloqueado (403) → trabalho só local até Contents:write.

### Commits locais nesta branch
| SHA | Mensagem |
| --- | --- |
| `39d3a13` | docs: add GANOH_GROK_PROGRESS.md (etapa 1 audit) |
| `c6bc3cb` | security: remove hard-coded WhatsApp/gestor/prazo defaults |
| `cd20459` | docs: ETAPA 3 security hardening progress |

## Próxima etapa
**ETAPA 4 — Baileys inbound** (`messages.upsert` + fila/outbox), sem ligar `WHATSAPP_SEND_ENABLED` / sem deploy. Continuar só em `ganoh/grok-whatsapp-ai`.

## Bloqueio operacional persistente
MCP `user-GitHub-xai` / Contents:write → **403**. Não tentar push/create remote branch até o usuário conceder permissão. Artefatos ficam locais em `/workspace/Ganoh1`.
