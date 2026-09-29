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

## Resumo financeiro e histórico do PDF — 29/09/2026

- Dashboard ganhou Resumo financeiro com Hoje, Semana, Mês e Ano.
- Cada período exibe receita, despesas registradas, resultado simples, pedidos e ticket médio.
- Dashboard também exibe recebíveis atuais, grupos em aberto, créditos de clientes, clientes cadastrados e produtos.
- Aba Gastos ganhou o período Semana e gráfico Receita x Gastos x Resultado simples.
- Histórico mensal/anual usa os agregados recuperados do PDF de 28/09/2026 e soma apenas movimentações novas posteriores.
- Semana usa somente dados diários factuais. Enquanto a janela de 7 dias alcançar o período anterior à migração, mostra aviso de cobertura parcial a partir de 29/09/2026.
- Terminologia corrigida para "Resultado simples", evitando apresentar receita menos despesas registradas como lucro contábil.
- Smoke de produção valida os pisos históricos do relatório: 2026 receita >= R$ 368.856,69; despesas >= R$ 56.008,18; setembro receita >= R$ 50.792,00; despesas >= R$ 11.331,55.
- Deploy validado: 196795b3abd3c0680851b22c69bd9c2b70bbec6c.


## Tema + gráficos financeiros — 29/09/2026

- Corrigido travamento ao alternar claro/escuro no Safari/iPhone: a animação agora possui fallback e nunca deixa `transitioning` preso.
- Gestor reaproveita sessão salva e carrega automaticamente o resumo financeiro.
- Data dos filtros financeiros usa calendário local, evitando deslocamento UTC no celular.
- Gráfico de vendas substituído por Recharts responsivo, com área, eixos legíveis e tooltip.
- Gráfico financeiro substituído por Recharts com barras de Receita/Gastos e linha de Resultado simples.
- Totais de Receita, Gastos e Resultado ficam visíveis abaixo do gráfico.
- Em telas pequenas, séries longas usam rolagem horizontal em vez de comprimir as colunas.
- Semana, Mês e Ano permanecem calculados a partir dos dados factuais disponíveis. Histórico recuperado do PDF antes da migração é mensal; semanas históricas não são inventadas.
- Deploy validado: `dep-dattvop42hec73d4ane0` / commit `0a78d1c5e657fe8506a66e66ce4ee89f38296efd`.
- Smoke de produção aprovado: site, gestor, resumo financeiro, menus, clientes, dívidas, despesas, gráficos anual/semanal e caixas.


## E2E completo de produção — 29/09/2026

Executado no próprio Render contra a API real em loopback, com registros temporários `E2E_TEST_*` e limpeza direta no Mongo em `finally`.

Aprovado 18/18:
1. health do servidor;
2. site público;
3. cardápios Runner e GYM Londres;
4. Gestor + gráficos semanais;
5. pedido real com total descontado;
6. pedido chegando à cozinha e rastreamento;
7. reflexo no Gestor e caixa;
8. fluxo received → preparing → ready → delivered + histórico;
9. venda manual criar/listar/excluir;
10. gasto criar → resultado semanal → excluir;
11. cliente de prazo/comanda;
12. adicionar valor/crédito + usar crédito;
13. pedido a prazo virando devedor;
14. adicionar valor com dívida e abatimento automático;
15. pagamento parcial de devedor;
16. quitação completa removendo da lista de devedores;
17. Gestor, gráficos e estoque após todas as escritas;
18. limpeza verificada: zero registros de teste restantes.

Resultado final no log: `GANOH E2E PASSED`.
O modo `GANOH_E2E_ONCE` foi desligado após o teste e o deploy final ficou LIVE.
Smoke somente leitura final também aprovado.
