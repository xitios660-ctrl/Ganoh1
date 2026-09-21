# Ganoh no Render

## O que está preparado

- Um serviço Docker com React, FastAPI e Baileys, sem mudar o layout do sistema.
- API e frontend no mesmo domínio; rotas internas da SPA funcionam ao recarregar.
- Baileys acessível apenas em localhost; rotas do painel exigem autenticação do gestor.
- Sessão do WhatsApp criptografada em MongoDB, com trava para evitar duas instâncias conectadas durante um redeploy.
- Reconexão com espera progressiva; logout exige um novo pareamento pelo painel.
- Nenhum envio de teste automático. O envio permanece desligado até a migração ser conferida.
- A inicialização não insere as duas vendas históricas de R$ 600,55 e R$ 416,00 e não troca senhas importadas automaticamente.

## Publicação

O `render.yaml` cria o serviço `ganoh1` no plano Free. Requer workspace confirmado, acesso do Render ao repositório e variáveis privadas preenchidas no Dashboard. Os dados usam um MongoDB persistente externo; não são armazenados no disco temporário do Render.

`MIGRATION_PENDING=true` publica apenas uma página de manutenção, sem carregar o sistema ou escrever no banco. O health check informa `migration_pending: true`; isso comprova apenas a infraestrutura, não a conclusão da migração.

Antes de liberar: preencher `MONGO_URL`, `DB_NAME`, `GESTOR_PASSWORD`, `PRAZO_PASSWORD` e `CLEAR_DATA_PASSWORD`. Preservar as credenciais e configurações usadas pela operação. Manter `WHATSAPP_SESSION_KEY` estável entre deploys; alterá-la impede ler a sessão salva. Nunca colocar segredos em commits ou mensagens.

As funcionalidades de IA e e-mail precisam das respectivas `EMERGENT_LLM_KEY` e `RESEND_API_KEY` válidas no novo ambiente. A distribuição Python da Emergent está fixada por URL e SHA-256 em `backend/requirements.txt`. A instalação de ambos os projetos Node usa os arquivos de lock.

## Migração integral

O HTML público não é um backup. Para transferir todos os dados de `https://charts-3.emergent.host`, é necessário acesso autorizado ao banco de origem ou um backup completo exportado pela Emergent. O script não usa senhas de exemplo nem tenta contornar o login.

1. Obter um backup da origem e preparar um banco de destino vazio com nome distinto. Não apontar o novo app diretamente para a origem sem uma decisão explícita.
2. Definir no ambiente `SOURCE_MONGO_URL`, `SOURCE_DB_NAME`, `TARGET_MONGO_URL` e `TARGET_DB_NAME`. O usuário da origem pode ser somente leitura.
3. Executar `python scripts/migrate_mongo.py` para conferir coleções e quantidades sem copiar.
4. Pausar gravações na origem, incluindo agendamentos, e executar `python scripts/migrate_mongo.py --apply --source-paused`.
5. O script copia documentos sem recalcular valores, preserva identificadores/tipos BSON/índices e compara quantidade e SHA-256 de cada coleção. Destino não vazio, dados alterados durante a cópia ou divergências interrompem a liberação. Não sobrescreve nem apaga a origem. Se falhar, manter o destino isolado e usar um novo banco vazio após investigar.
6. Conferir no painel os totais das duas unidades, clientes, devedores, créditos, pagamentos, estoque, despesas, histórico, PIX e caixa. Só então mudar `MIGRATION_PENDING=false` e fazer novo deploy.
7. Manter a origem disponível como referência até aceitar a conferência final. Não operar dois caixas simultaneamente durante a troca.

Coleções especiais (views, capped e time-series) requerem backup/restauração nativos do MongoDB; o script recusa transformá-las silenciosamente.

## WhatsApp

Após liberar o sistema, entrar no gestor, abrir WhatsApp e usar **Gerar QR Code**. Parear com o número correto no celular. Selecionar o grupo e salvar. Conferir separadamente `WHATSAPP_GROUP_RUNNER` e `WHATSAPP_GROUP_ID` (GYM Londres), preservando os destinos autorizados.

Só habilitar `WHATSAPP_SEND_ENABLED=true` depois de conferir os dados, o número pareado e os destinos. Habilitar `SCHEDULER_ENABLED=true` para retomar os agendamentos existentes no momento combinado da troca; eles também podem alterar o estado dos pedidos.

O plano Free pode hibernar por inatividade, interrompendo o WhatsApp. A sessão é persistida, mas conexão contínua exige infraestrutura que permaneça ativa. Não foi contratado plano pago.

## Verificação

`npm ci --legacy-peer-deps && npm run build` em `frontend`.

`npm ci && npm test` em `whatsapp`.

`python -m pytest backend/tests/test_render_deployment.py` e `python -m compileall -q backend scripts`.

O pareamento real e a conferência dos dados só podem ser declarados concluídos após acesso autorizado à origem e ao serviço publicado.
