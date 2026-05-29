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

## Implemented (29/05/2026)
- Codebase do Ganohbebe-main descompactado para `/app` (backend + frontend)
- Dependências instaladas (yarn + pip)
- `/app/backend/.env` e `/app/frontend/.env` criados com `MONGO_URL`,
  `DB_NAME=ganoh_db` e `REACT_APP_BACKEND_URL` do preview
- **Dados importados do site de referência** via os scripts `import_from_prod.py`
  e `sync_from_reference.py`:
    - 79 itens de menu custom (Runner 27 + Gym 52)
    - 14 adicionais globais
    - 113 itens de estoque (Runner 55 + Gym 58)
    - 122 despesas (R$ 23.125,79)
    - 82 clientes prazo (Runner 69 + Gym 13)
    - 517 pedidos prazo pendentes com status `prazo_pending`
      (excluídos dos gráficos para não duplicar)
    - 3.150 pedidos sintéticos gerados a partir dos agregados diários
      do site fonte → gráficos mensais/anuais com contagens próximas
      e ranking de "Mais Vendidos" idêntico ao da origem
    - Cash drawer config sincronizada por loja
    - Charge messages (mensagens de cobrança Prazo) por loja
- Patch em `sync_from_reference.py`: `order_total` usa o valor-alvo exato
  do agregado diário (evita over-shoot de receita) e status de prazo
  muda para `prazo_pending`.
- Senha do gestor: `ganoh2024` (seed na inicialização do backend cria
  tenant `gestor` automaticamente)

## Data Parity (vs prazo-payment-sys.emergent.host)
- ✅ Expenses: 122 / R$ 23.125,79 (idêntico)
- ✅ Stock: 55 + 58 (idêntico)
- ✅ Prazo customers: 69 + 13 (idêntico)
- ✅ Sales by category list & ordering: idêntico
- ✅ Top sellers (ranking): Água Pequena, Chiclete, Paçoquita,
  Café Pequeno, Energético Monster, Café Grande... (mesma ordem)
- 🟡 Yearly chart counts: local ~95% do source (origem inclui prazo
  no yearly mas exclui no monthly; replicamos a visão monthly)

## Routes (Frontend)
- `/` Store selector (Runner / Gym / Área Administrativa)
- `/auth` Painel do Gestor (login)
- `/gestor/dashboard` Dashboard com gráficos, vendas, caixa, gastos
- `/:store` Cardápio
- `/:store/cozinha` Cozinha
- `/:store/estoque` Estoque
- `/:store/live` Live dashboard
- `/equipe` Acesso da equipe

## Next Action Items
- [ ] Verificar fluxo de pagamento prazo (recebe/abate) via UI
- [ ] Confirmar gráfico anual mostra dados de Mar/Abr/Mai 2026 corretamente
- [ ] Re-sincronizar dados se a fonte for atualizada
  (rodar: `cd /app/backend && python sync_from_reference.py`)

## Backlog
- Implementar paginação completa da history para chegar a 100% dos pedidos reais
- Adicionar cache em endpoints pesados (yearly/monthly)
