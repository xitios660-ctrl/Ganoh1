# API central v1 — homologação isolada 0.4.0

Não é montada em `backend/server.py`, não lê `.env`, não acessa Render e rejeita nomes fora de `ganoh_sync_test_*`. `create_app(db, owner_origins=())` recebe banco/cliente PyMongo gerenciados pelo chamador. Não iniciar servidor legado para estes testes. Nenhuma implantação foi feita.

## Escritas e idempotência

`POST /api/sync/v1/batch`, bearer por dispositivo, corpo `{"operations":[evento de OfflineJournal.pending()]}`. Identidade fixa em `devices` com token hash, unidade, revogação e permissões explícitas por tipo comercial; tokens de fixtures não servem para uso real.

Inbox única por unidade+UUID; venda por unidade+sale_id; recibo de recebimento por unidade+referência normalizada. Hash recalculado, nunca aceito apenas por declaração do cliente. Transação une efeito, livro balanceado, inbox e recibo, com leitura snapshot/write concern majority. Reenvio após resposta perdida retorna o mesmo recibo; `already_applied` não repete efeito. Lote pode confirmar parcialmente; repetir os mesmos eventos é seguro.

Revogação é serializada por escrita no dispositivo. Guard de unidade serializa efeitos de dispositivos da mesma loja para impedir overdraft/write-skew. RUNNER/GYM LONDRES nunca compartilham saldos nem permissões implicitamente.

Vendas em dinheiro/prazo aprovado exigem preço/estoque/versão autoritativos; prazo exige cliente, versão e limite aprovado. Livro registra venda em receita e caixa ou recebível. Receber dívida aumenta caixa e reduz recebível sem repetir receita. PIX/cartão não são liquidados automaticamente.

Operações em `desktop.business_rules.KINDS`: suprimento/retirada/despesa, cliente/limite/recebimento, abertura/fechamento/reconciliação de caixa, cadastro de produto, ajuste de estoque e estado de cozinha. Cada tipo exige permissão no dispositivo, verificada novamente na transação. Auditoria individual local não substitui essa autorização central.

Fechamento com diferença mantém saldo e exige revisão; reconciliação é novo evento balanceado em cash/cash_variance com motivo. Versão/estoque/prazo divergentes geram conflito durável sem efeitos comerciais silenciosos. Rejeitar conflito não apaga o diário local.

## Snapshots e revisão

`GET /api/sync/v1/snapshot?cursor=...&operation_ids=...`: captura imutável, páginas de 100, máximo 1.000 SKUs, validade 24h, cursor vinculado a dispositivo/unidade. Até 100 UUIDs solicitados; cobertura inclui fingerprints de efeitos já confirmados. Cliente publica somente ao completar staging, retoma cursor e projeta operações ainda não cobertas. Não fornece snapshot de clientes/saldos nesta versão.

`POST /api/sync/v1/conflicts/review`: proprietário com unidades autorizadas, review_id, operation_id, unit, expected_revision, reason e decisão reject/retain. Inbox/revisão confirmam atomicamente, recibo original imutável. Sem reaplicação financeira automática. UI completa de revisão e download de resoluções continuam pendentes.

## Proprietário

Provisionar apenas no banco isolado com `owner_auth.provision(db,username,password,units)`. Sem cadastro público ou senha padrão. Login em `/api/sync/v1/owner/login`, sessão aleatória armazenada por hash com validade de 8h, bloqueio após falhas, logout/revogação. Bearer independente do dispositivo; unidades explicitamente permitidas. Origens CORS devem ser HTTPS e declaradas em owner_origins.

`GET /api/sync/v1/owner/overview`: somente livro central confirmado, por unidade/consolidado, horário de contato/sync e alerta de atraso. Quantidade local pendente é desconhecida (null); consulta do proprietário não renova contato da loja. `GET /api/sync/v1/owner/stock?unit=...&cursor=...` fornece snapshot paginado vinculado ao proprietário/unidade.

Novo build gestor usa `REACT_APP_OWNER_PANEL=true` e `REACT_APP_SYNC_ORIGIN=https://central-de-homologacao`. Não substitui dashboard legado nem consulta ganoh_production. Interface pode ser estática, mas login/sync precisam de backend HTTPS separado. Infraestrutura, limites de ingresso/rate limiting, retenção, provisionamento/rotação reais e integração de autorização legada ainda exigem projeto/homologação.

## Reprodução

Instalar requirements-test.txt e desktop/requirements.txt. Iniciar MongoDB 7 descartável em loopback 27028 com replica set rs0 (workflow contém comandos). Testes criam/apagam somente bancos aleatórios de ensaio:

```sh
python -m unittest discover -s backend/sync_v1/tests -v
```

TestClient não comprova servidor HTTPS externo. Transporte Windows exige TLS/certificados e não segue redirects. Ensaios Chromium e instruções adicionais: [demonstração](../../desktop/DEMONSTRATION.md). Resultados: [relatório](../../docs/CODEX_WINDOWS_PROGRESS_2026-11-18.md).

## Contas exclusivas de Android TV (0.2)

Proprietário autenticado administra GET/POST /owner/tv-accounts e POST /owner/tv-accounts/{id}/revoke sob /api/sync/v1. Usuário minúsculo de 3–64 caracteres, senha dedicada de 12–256 diferente da senha do proprietário e unidades explícitas. Máximo 20 contas ativas por proprietário; lista prioriza ativas e mostra até 100 registros. Cadastro/revogação com auditoria atômica e confirmação majority.

TV usa /tv/login, /tv/logout, /tv/overview e /tv/stock. Sessões/contas separadas, scrypt, lockout de 15 min após 5 falhas, sessão de 8h por hash e token tv:read rejeitado pelas autorizações de proprietário/dispositivo. Cada consulta revalida conta, proprietário e unidades atuais. Cursores de estoque são vinculados à identidade TV, sem compartilhamento com outras TVs ou proprietário. Rotas owner/tv retornam Cache-Control no-store, inclusive erros de autenticação.

A revogação protege a próxima consulta; valores já recebidos ficam em memória, com aviso de atraso, até sair/trocar de aplicativo ou receber uma rejeição de sessão da central. Não há apagamento remoto da tela enquanto a TV estiver sem conexão. O aplicativo marca dados antigos e limpa a tela ao sair/trocar de aplicativo. Sem deploy: guard ganoh_sync_test_* permanece, sem alterações em backend/server.py, Render ou produção. Consulte tv/README.md.
