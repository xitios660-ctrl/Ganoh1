# GANOH_PROGRESS.md

## Etapa atual
**Migração Render + MongoDB: operacional e validada em 29/09/2026.**

## Produção da migração
- Serviço Render: `ganoh1`
- URL: https://ganoh1-tbmo.onrender.com
- Branch: `main`
- WhatsApp: fora da validação funcional desta etapa, conforme combinado.

## Concluído
- Banco MongoDB conectado e persistente.
- Recuperação do relatório de 28/09/2026 verificada no banco.
- Recuperados: 93 clientes, 470 débitos, 697 itens de débito, 301 gastos e 320 itens de cardápio.
- Total a prazo recuperado e verificado: R$ 6.943,15.
- Histórico mensal de vendas recuperado separadamente dos pedidos vivos.
- Tela de preparação não aparece com a migração liberada.
- Acesso “Sou da equipe” corrigido para validar senha no backend, sem embutir segredo no JavaScript.
- Caixa corrigido para encerrar o período ao fazer retirada total.
- Venda manual em dinheiro usa o horário real de entrada no caixa via `cash_recorded_at`.
- Regressão coberta: retirada total seguida de entrada de R$ 5,00 deve resultar em R$ 5,00 no caixa.

## Validação
- Docker build executa testes de caixa antes de publicar.
- 37 testes passaram no build de 29/09/2026.
- Smoke test de produção passou após o deploy:
  - site
  - gestor
  - 2 cardápios
  - clientes
  - dívidas
  - gastos
  - gráficos anual e semanal
  - caixas
- Último deploy validado: `dep-datsun6gekts73c4gl5g`
- Commit implantado: `319d70d02a53ce7c6e7fdae9a922d34d72ebd415`

## Arquivos alterados nesta etapa
- `backend/server.py`
- `frontend/src/pages/StaffAccessPage.js`
- `backend/tests/test_cash_full_withdrawal_regression.py`
- `Dockerfile`
- `.dockerignore`
- `render.yaml`

## Decisões
- Não reconstruir o sistema do zero.
- Não apagar nem substituir dados recuperados.
- Não usar o WhatsApp como requisito para liberar esta etapa.
- Manter testes de regressão do caixa como gate do build.
- Segredos permanecem apenas no servidor/Render, nunca no frontend ou no repositório.

## Pendências
- WhatsApp/Baileys: revisar em etapa separada.
- Fazer validação visual manual do fluxo da equipe em celular/desktop caso apareça diferença de layout.

## Otimização de desempenho — 29/09/2026

- Cozinha: carregamento inicial separado em dados operacionais e dados secundários.
- Cozinha: tela deixa de aguardar inicialização de estoque antes de abrir.
- Cozinha: polling de 6s reduzido de 13 requisições para apenas os 3 endpoints operacionais (pedidos, status e PIX pendente).
- Cozinha: histórico, estoque, prazo, cardápio, caixa e demais dados carregam em segundo plano e continuam disponíveis.
- Gestor: acesso com sessão salva pula a validação redundante de /auth/check e abre direto no dashboard.
- Gestor: endpoint /api/gestor/dashboard paralelizado para consultar as duas lojas e fontes independentes do MongoDB simultaneamente, mantendo o mesmo contrato de resposta.
- Frontend production build: aprovado.
- Backend regression suite: 40 testes aprovados.
- Smoke de produção após deploy: aprovado para site, gestor, 2 menus, clientes, dívidas, gastos, gráficos anual/semanal e caixas.
- Deploy validado: commit 2a937d171453b0d29e9ef567551aeac3dd2a9bc4.
