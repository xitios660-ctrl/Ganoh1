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
- Falta provisionamento seguro, limites de corpo no ingresso, rate limiting, snapshots/cursor, heartbeat, retenção, revisão de conflitos, rotação de token e integração com autorização do proprietário.

## Reprodução

Instalar `requirements-test.txt`; iniciar MongoDB 7 descartável em `127.0.0.1:27028` com replica set `rs0` (comandos completos no workflow). Executar da raiz:

```sh
python -m unittest discover -s desktop/tests -v
python -m unittest discover -s backend/sync_v1/tests -v
```

Os testes criam nomes aleatórios `ganoh_sync_test_*` e apagam apenas esses bancos ao terminar. Não usam Atlas ou fixtures de produção. O transporte desktop exige HTTPS, valida certificados e não segue redirects; testes de integração usam TestClient, sem expor uma API HTTP na rede.

## Decisão Windows

Manter Electron como escolha inicial: reutiliza React/CRA e permite gerenciar o processo Python empacotado sem exigir WebView2 e toolchain Rust. O custo de memória e tamanho será medido no piloto; ainda não existe instalador. Pré-requisitos para empacotar: autenticação loopback, SQLCipher/DPAPI, migrações versionadas, paridade comercial e testes reais de atualização preservando dados.
