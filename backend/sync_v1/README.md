# API central v1 — homologação isolada

Não é montada em `backend/server.py`, não lê `.env`, não acessa Render e rejeita qualquer nome de banco fora de `ganoh_sync_test_*`. Sem comando de provisionamento em produção. `create_app(db)` recebe um cliente PyMongo compartilhado e gerenciado pelo chamador. Não iniciar o servidor legado para executar estes testes.

## Contrato e limites

`POST /api/sync/v1/batch`, `Authorization: Bearer <token por dispositivo>`, corpo `{"operations": [evento de OfflineJournal.pending()]}`. Resposta `{"results": [...]}` compatível com `sync_once`. Token aleatório de alta entropia deve ser provisionado fora do código; somente SHA-256 do token fica em `devices`, com `_id`, `unit` e `revoked: false`. Tokens dos testes são fictícios e inadequados para instalações reais.

- Inbox exclusiva por unidade + UUID; venda exclusiva por unidade + sale_id, inclusive entre dispositivos. Hash recalculado no servidor, nunca aceito apenas por declaração do cliente.
- Cada operação tem transação independente: inbox/recibo, venda e baixa de estoque confirmam juntos com write concern majority e leitura snapshot. Um lote pode confirmar parcialmente; após erro, repetir todos os mesmos UUIDs é seguro.
- Uma escrita transacional no dispositivo serializa revogação e sincronização. Revogar não desfaz operações já confirmadas.
- Só venda em dinheiro com catálogo de homologação autoritativo. Cada item requer `sku`, `quantity` inteiro positivo e `base_version`. Catálogo contém unidade, SKU, preço em centavos, quantidade e versão. Sem estoque implícito ou preços enviados pelo cliente.
- Estoque insuficiente, versão divergente, preço divergente e reutilização de sale_id por outro UUID geram conflito durável sem efeitos financeiros/estoque. Reenvio devolve o mesmo conflito. Resolver exige futuro fluxo auditável; nunca editar payload ou regenerar UUID para tentar contornar um conflito.
- PIX, cartão e prazo vão para revisão sem liquidação automática. Recebimentos, estornos, despesas e caixa ainda não implementados. Não existe paridade com o GANOH comercial.
- Coleções `sales`, `stock`, `inbox`, `devices` são exclusivas deste ensaio. Vendas NÃO alimentam o dashboard legado e NÃO representam consolidação no painel do proprietário.
- Há snapshots imutáveis de catálogo/estoque com cursor e revisão auditável limitada a rejeitar/manter conflitos. Faltam provisionamento seguro, limites de corpo no ingresso, rate limiting, CDC de todas as coleções, heartbeat, retenção de auditoria, aprovação financeira de conflitos, rotação de token e integração com a autorização do proprietário existente.

## Reprodução

Instalar `requirements-test.txt`; iniciar MongoDB 7 descartável em `127.0.0.1:27028` com replica set `rs0` (comandos completos no workflow). Executar da raiz:

```sh
python -m unittest discover -s desktop/tests -v
python -m unittest discover -s backend/sync_v1/tests -v
```

Os testes criam nomes aleatórios `ganoh_sync_test_*` e apagam apenas esses bancos ao terminar. Não usam Atlas ou fixtures de produção. O transporte desktop exige HTTPS, valida certificados e não segue redirects; testes de integração usam TestClient, sem expor uma API HTTP na rede.

## Decisão Windows

Manter Electron como escolha inicial: reutiliza React/CRA e permite gerenciar o processo Python empacotado sem exigir WebView2 e toolchain Rust. O custo de memória e tamanho será medido no piloto; ainda não existe instalador. Pré-requisitos para empacotar: autenticação loopback, SQLCipher/DPAPI, migrações versionadas, paridade comercial e testes reais de atualização preservando dados.

## Continuação: snapshots e revisão

`GET /api/sync/v1/snapshot?cursor=...` captura até 1.000 SKUs numa geração imutável com páginas de 100 itens e expiração de 24h. Cursor é vinculado ao dispositivo/unidade; a retomada usa a mesma geração. SQLite publica somente o catálogo completo, valida versões e mantém operações locais separadas.

`POST /api/sync/v1/conflicts/review` usa credencial independente de `reviewers`, permitida por unidade e revogável; exige `review_id`, `operation_id`, `unit`, `expected_revision`, `reason` e `decision` (`reject` ou `retain`). Revisão de inbox + evento auditável são atômicos. Não aplica pagamentos/estoque e não altera recibos originais. A UI de revisão do proprietário e a transmissão dessas revisões ao desktop continuam pendentes.

Demonstração local, criptografia e estrutura Windows: `desktop/DEMONSTRATION.md`. Os testes de integração agora incluem o ciclo API local → reinício → API central real e retomada de três páginas com alteração concorrente do catálogo.

## Livro comercial 0.3.0

Além de venda em dinheiro, o batch aceita `cash.deposit`, `cash.withdraw`, `expense.create`, `customer.create` e `prazo.receive` quando autorizados explicitamente em `devices.permissions`. A autorização é reconferida na transação. Inbox, recibo, lançamentos balanceados e efeito comercial confirmam juntos; um guard por unidade impede write-skew de saldo entre dispositivos. `payment_reference` de recebimento é único por unidade (normalizado por casefold/trim), mesmo com outro UUID/business_id. Recebimento exige dívida existente e não concede crédito nem liquida PIX/cartão.

Coleções adicionais são exclusivas do ensaio: ledger, business_events, customers, payment_refs e unit_state. Não há backfill automático de saldos de demonstrações anteriores nem integração com o dashboard legado. Os testes usam dívidas históricas fictícias para recebimentos; snapshots de clientes/dívidas e venda a prazo ainda faltam. Ver detalhes e limitações em `desktop/DEMONSTRATION.md` e `docs/DESKTOP_PARITY.md`.
