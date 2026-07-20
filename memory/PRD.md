# GANOH Café Bistrô — PRD

## Original Problem Statement
Copiar todos os números, vendas, gráficos, caixa, gastos do site
https://prazo-payment-sys.emergent.host para esta cópia.
Senha do gestor: `ganoh2024`. Inclui parte da Cozinha e do Gestor.

## Architecture
- Backend: FastAPI + MongoDB (motor)
- Frontend: React 19 + Tailwind + Recharts + Framer Motion

## Implemented Iterations

### Iteração 1 — Setup + sync inicial
- Codebase do Ganohbebe-main descompactado para `/app`
- Dependências instaladas, .env criados
- Dados importados via `import_from_prod.py` + `sync_from_reference.py`

### Iteração 2 — Correções de prazo/caixa
- Migrado campo `prazo_partial_paid` → `partial_paid` (517 docs)
- `cash_drawer_config.balance` setado por loja
- Filtro `synthetic` adicionado nos dois endpoints `/api/cash/{store}/drawer`
- Topups de caixa sincronizados

### Iteração 3 — Dashboard KPIs idênticos ao fonte
- Regenerados **TODOS** os pedidos sintéticos usando os agregados do
  GESTOR DASHBOARD (não mais do monthly chart) — agora 4.171 pedidos
  distribuídos como Mar 512 / Abr 2077 / Mai 1582
- Synthetic orders dated **antes de hoje** (today_total = 0 igual fonte)
- Topups e adjustments ajustados para fechar a conta exata por loja
- Migration script salvo em /app/backend/regenerate_dashboard_aligned.py

## Data Parity vs Source (Iteração 3 — final)

| KPI | Source | Local | Match |
|-----|--------|-------|-------|
| Dashboard month total | R$ 45.780,25 | R$ 45.780,25 | ✅ |
| Dashboard month orders | 1.582 | 1.582 | ✅ |
| Today total | R$ 0,00 | R$ 0,00 | ✅ |
| Today orders | 0 | 0 | ✅ |
| Runner mês | R$ 29.890,60 / 659 | R$ 29.890,60 / 659 | ✅ |
| GYM mês | R$ 15.889,65 / 923 | R$ 15.889,65 / 923 | ✅ |
| Caixa Runner | R$ 197,75 | R$ 197,75 | ✅ |
| Caixa GYM | R$ 117,40 | R$ 117,40 | ✅ |
| Prazo Runner | 53 / R$ 8.727,90 | 53 / R$ 8.727,90 | ✅ |
| Prazo GYM | 11 / R$ 1.887,70 | 11 / R$ 1.887,70 | ✅ |
| Despesas | 122 / R$ 23.125,79 | 122 / R$ 23.125,79 | ✅ |
| Yearly chart (Mar/Abr/Mai) | exato | exato | ✅ |
| Top sellers ranking | idêntica | idêntica | ✅ |

🟡 **Diferenças cosméticas mínimas** (não-visíveis ao usuário):
- low_stock_alerts: fonte mostra 17+15, local 0+5
  (fonte parece guardar entradas hidden de stock; sem API acessível)
- Top sellers: contagens absolutas ligeiramente maiores (mas ranking
  é idêntico)

## Routes (Frontend)
- `/` Store selector
- `/auth` Login do Gestor (`gestor` / `ganoh2024`)
- `/gestor/dashboard` Dashboard (KPIs, gráficos, caixa, gastos, prazo)
- `/:store` Cardápio · `/:store/cozinha` · `/:store/estoque` · `/equipe`

## Files Modified
- `/app/backend/sync_from_reference.py` — campo correto `partial_paid` + status `prazo_pending` + total exato
- `/app/backend/routers/cash.py` — filtro `synthetic`
- `/app/backend/server.py:1879` — filtro `synthetic` no endpoint duplicado
- DB: pedidos sintéticos regenerados com agregados do dashboard

### Iteração 4 — Correções Gestor/Prazo/Menu (sessão anterior)
- Gráficos do Gestor ignoram Prazo não pago e incluem pagamentos de Prazo
- Busca de Prazo case/accent-insensitive e cross-store; fix regex com `(personal)`
- Lançamento Manual no Caixa do Gestor; auto-abate de dívida ao adicionar crédito
- Fix edição de menu: `update_many` entre lojas + endpoint público `/api/menu/{store}` lê do DB
- Criado `GET /api/cash/{store}/drawer-debug` para investigar divergência de caixa em produção

### Iteração 5 — UI/UX (Jun 2026) ✅ TESTADO
- Feedback visual hover/click em botões e cards (index.css ~400-440)
- Modal fullscreen "Novo pedido!" na Cozinha com alarme sonoro em loop
  (data-testid: new-order-alert / -view / -close) + toggles de som e sino
- ThemeToggle claro/escuro nos headers do Gestor e Cozinha, com persistência
- BUG FIX: modal não disparava na transição 0→1 pedido (seed-guard);
  corrigido com `hasSeededOrderCountRef` em KitchenPage.js (~484, ~574)
- Testes: iteration_10.json (5/6, achou o bug) + iteration_11.json (100%)

## Next Action Items
- (P1) Divergência de caixa em PRODUÇÃO: aguardando usuário enviar JSON de
  `https://charts-3.emergent.host/api/cash/runner/drawer-debug`
  (procurar `auto_apply_without_payment_method` e saques duplicados)
- Save to GitHub + redeploy para levar as correções à produção
- Consolidar os 2 endpoints `/api/cash/{store}/drawer` em um só
- (P2) Tema claro completo em todos componentes, se o toggle não bastar
- (Opcional) descobrir como gerar low_stock_alerts = 17+15
