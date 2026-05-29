# GANOH Café Bistrô — PRD

## Original Problem Statement
Abra o código e quero que copie os "números, vendas, gráficos, caixa, gastos, etc..."
do site https://prazo-payment-sys.emergent.host/ para esta cópia.
Todas as páginas devem mostrar os mesmos valores. Senha do gestor: `ganoh2024`.
A aplicação possui parte da cozinha e parte do gestor — tudo deve estar correto.

## Architecture
- Backend: FastAPI + MongoDB (motor) + APScheduler + Green API (WhatsApp)
- Frontend: React 19 + Tailwind + Recharts + Framer Motion
- Deploy: 0.0.0.0:8001 (backend) / 3000 (frontend) via supervisor

## User Personas
1. **Cliente** – navega o cardápio, faz pedidos
2. **Cozinha** – recebe e gerencia pedidos (Runner / GYM Londres)
3. **Gestor** – painel admin com KPIs, gráficos, caixa, gastos, prazo, etc.

## Implemented

### Iteração 1 (29/05/2026) — Sync inicial
- Codebase do Ganohbebe-main descompactado para `/app`
- Dependências instaladas, .env criados
- Dados importados do site fonte (menu 79 itens, estoque 113, despesas 122/R$23.125,79,
  prazo customers 82, prazo orders 517, cash drawer config, charge messages)
- 3.150 pedidos sintéticos gerados para alimentar os gráficos mensais/anuais
- Patch em `sync_from_reference.py`: status `prazo_pending`, `order_total` exato

### Iteração 2 (29/05/2026) — Correções de paridade
- 🐛 **PRAZO**: campo `prazo_partial_paid` corrigido para `partial_paid` em 517 pedidos
  (o endpoint /api/prazo/debts agora subtrai corretamente os pagamentos parciais).
  Totais batem EXATO com o site fonte: Runner R$ 8.727,90 / GYM R$ 1.887,70.
- 🐛 **CAIXA**: 
  - `cash_drawer_config` agora grava `balance` (campo lido pelo endpoint)
  - Pedidos sintéticos excluídos do cálculo via flag `synthetic`
  - Inseridos topups de venda em dinheiro + saídas sincronizadas
  - Resultado EXATO: Runner R$ 197,75 / GYM R$ 117,40
- ✅ Tab Prazo carrega sem o erro React `removeChild`/`NotFoundError`
- Verificado via testing agent (100% backend e frontend)

## Data Parity vs prazo-payment-sys.emergent.host
- ✅ **Expenses**: 122 / R$ 23.125,79 (idêntico)
- ✅ **Stock**: 55 + 58 (idêntico)
- ✅ **Prazo customers**: 69 + 13 (idêntico)
- ✅ **Prazo debts**: R$ 8.727,90 + R$ 1.887,70 (idêntico)
- ✅ **Cash drawer**: current=197,75 + 117,40 (idêntico)
- ✅ **Sales by category list & ranking**: idêntico
- ✅ **Top sellers ranking**: idêntico
- 🟡 Yearly chart counts: ~95% (fonte inclui prazo no anual mas exclui no mensal)

## Routes (Frontend)
- `/` Store selector
- `/auth` Login do Gestor
- `/gestor/dashboard` Dashboard completo (gráficos, vendas, caixa, gastos, prazo)
- `/:store` Cardápio
- `/:store/cozinha` Cozinha
- `/:store/estoque` Estoque
- `/equipe` Acesso da equipe

## Files modified (iteração 2)
- `/app/backend/sync_from_reference.py` — campo correto `partial_paid`
- `/app/backend/routers/cash.py` — filtro `synthetic` nas queries
- `/app/backend/server.py` — filtro `synthetic` na duplicata do endpoint /cash/{store}/drawer
- DB: migração `prazo_partial_paid` → `partial_paid` (517 docs);
       `cash_drawer_config.balance` setado por loja;
       topup orders e withdrawals sincronizadas

## Next Action Items
- Consolidar os DOIS endpoints `/api/cash/{store}/drawer` em um só
- Replicar a fix para deployments existentes (ex.: charts-3) via Save to GitHub
- Validar fluxos de pagamento prazo (add/remove valor, abater) na UI

## Backlog
- Cache em `/api/gestor/chart/*` para latência
- Paginação completa do histórico real
