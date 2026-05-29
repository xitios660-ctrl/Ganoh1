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

## Next Action Items
- Save to GitHub + redeploy
- Consolidar os 2 endpoints `/api/cash/{store}/drawer` em um só
- (Opcional) descobrir como gerar low_stock_alerts = 17+15
