# GANOH Windows — dados reais e prontidão — 22/11/2026

Status: desenvolvimento; PR #6 deve continuar rascunho. Nenhum instalador deste
incremento constitui entrega final com histórico real. O pedido inclui todas as
vendas antigas e recentes, inclusive sábado 21/11, sem interromper o site.

## Alterações

- `backend/data_bridge/{archive,mongo_backup,unit_export}.py`: backup consistente
  BSON completo e criptografado; ensaio de restauração local com conferência;
  projeção estrita por unidade somente depois de validar o arquivo exato.
- `backend/data_bridge/tests/*`: testes reais contra Mongo descartável, incluindo
  alteração simultânea na origem, índices/views, documentos históricos que já
  não passam no validador atual, adulteração e recusa de destinos existentes.
- `backend/import_from_prod.py`: aposentado o importador legado que substituía
  coleções e continha credencial fixa. Não foi usado. Remover do HEAD não limpa
  o histórico Git nem revoga a credencial antiga; revisão da credencial pelo
  proprietário permanece pendente, sem alteração automática na produção.
- `desktop/legacy_data.py`: cache histórico SQLCipher, preservação BSON, páginas
  retomáveis, versões imutáveis, escopo da unidade e publicação integral atômica.
- `desktop/{offline_store,commerce}.py`: schema 4 ao iniciar carga histórica;
  bloqueio de novas operações até conciliar saldo inicial, inclusive carga
  interrompida. Reenvio de UUID já registrado continua permitido.
- `desktop/snapshots.py` e teste de operações: corrigida perda da cobertura de
  operações de estoque entre páginas. Retomada não desconta novamente a venda.
- Requisitos, `.gitignore` e workflow de regressão atualizados. Arquivos privados
  de backup não devem existir no repositório, ainda que ignorados.

## Verificação local executada

- Data bridge: 13 testes aprovados em MongoDB 7 descartável.
- Sincronização central: 32 testes aprovados.
- Desktop: 63 testes, 61 aprovados e 2 exclusivos de Windows ignorados no Linux.
- Fixtures incluem histórico de 2020, registros de sábado 21/11/2026, dinheiro
  Decimal128, duas unidades, interrupções e reabertura. Nenhuma fixture real.
- CI do commit dfe570e aprovada: 63 desktop Windows, Linux 61+2 skips,
  32 central, 13 data bridge, 13 React e 2 Node; builds desktop/gestor aprovados.
  https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44982071812
- Instalador deste commit aprovado: PyInstaller, restart e ensaio NSIS de
  instalação/reinstalação/desinstalação preservando os dados.
  https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44982071817
  Isso não representa teste físico nas lojas nem importação do banco real.
- Workflow Android TV disparado pelo PR (sem mudanças Android): falha inicial
  no download Maven; repetição aprovada, incluindo testes/emulador existentes.
  https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44982075599

## Limitações que impedem entrega final

O site informado `https://ganoh-minjuin.onrender.com/` respondeu HTTP 200. Ainda
não há backup dos dados reais neste incremento. Após
confirmação do proprietário, consulta somente leitura localizou ganoh-minjuin
em “Min's workspace”, conexão Minjuin, serviço srv-dc057df40ujc73fe2fig.
O serviço aponta para este repositório/main e está com auto-deploy desligado.
Nenhuma configuração foi alterada.

O conector Render não oferece leitura de variáveis de ambiente; não se usou
update de variáveis como contorno. A tentativa de navegador falhou antes de
abrir o painel. Consulta apenas dos nomes de bancos nos dois clusters da conexão
Atlas Primary não encontrou ganoh_production; nenhum documento de outras
aplicações foi consultado. Posteriormente o proprietário identificou a conexão
Atlas Regex. Nela foi encontrado ganoh_production no Project 0 / Cluster0,
MongoDB 8.0.39, Free. Consultas somente leitura confirmaram 22 coleções, unidades
runner/gym-londres e vendas até sábado 21/11. Valores, contagens comerciais,
clientes e documentos reais não foram colocados no repositório público.

A inspeção revelou prazo_debts, prazo_payment_reversals e coleções administrativas
que não existiam no inventário do código. A projeção inclui dívidas e estornos;
auditorias globais repair_runs/recovery_runs e filas Baileys ficam somente no
backup integral do servidor, nunca no pacote de funcionário. Coleções novas não
mapeadas continuam bloqueando a exportação. Estornos com pedidos/pagamentos
aninhados de outra unidade são recusados, também na carga SQLCipher.

O conector de consultas não fornece exportação BSON com sessão snapshot nem
credenciais ao cliente Python. Não tratar consultas paginadas independentes como
backup consistente. Para executar capture/validate_restore reais está preparado
um acesso dedicado: usuário ganoh_backup_reader_20261122, somente role read em
ganoh_production, limitado a Cluster0, senha gerada pelo servidor MCP e guardada
fora do Git; liberação somente do IP de saída atual /32, sem trocar entradas
existentes. Nenhum usuário/IP foi criado. O proprietário autorizou expressamente esse acesso
na sessão; entretanto atlas_create_db_user recusou a execução com a mensagem
“User did not confirm the execution”, informando que a operação não foi realizada.
Não tentar outro mecanismo de escrita para contornar a confirmação do conector.
É preciso concluir essa confirmação da ferramenta ou disponibilizar acesso
somente leitura por canal seguro. Nenhuma senha deve ser enviada no chat.
Revalidar IP antes de executar. A ferramenta
de criação não oferece expiração/revogação; revogar usuário e IP pelo painel Atlas
ao terminar a cópia, com confirmação do proprietário. Jamais incluir o acesso no
Windows ou em artefatos. Até essa autorização, somente consultas via conector.

Testes locais deste ajuste: 15 data_bridge aprovados; desktop 64 executados,
62 aprovados e 2 skips exclusivos Windows. CI d9bfd75 aprovada com 64 testes
Windows, Linux 62+2 skips, 32 central, 15 data_bridge, 13 React, 2 Node e builds.
https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44985490393
Instalador d9bfd75 aprovado, incluindo restart do backend empacotado, instalação,
reinstalação e desinstalação preservando dados/chave.
https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44985490420
Android TV sem alterações: regressão/emulador aprovados nesta revisão.
https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44985494592
Esses testes não constituem validação física nas lojas nem carga real de histórico.

O cache histórico não está ligado ao assistente de primeira execução nem às APIs
originais. Faltam conciliação de caixa/prazo/estoque, compatibilidade integral com
os módulos/telas web, captura das mudanças posteriores ao snapshot, integração
idempotente com o backend real e validação do instalador nos computadores das
lojas. Não se deve transformar o histórico em vendas novas para preencher a UI.

O snapshot representa um instante, não garantia de dados futuros atualizados.
A entrada em operação exige comparar contagens, totais financeiros e últimas
operações por unidade, aplicar as mudanças posteriores com revisão dos conflitos
e confirmar a sincronização ao painel remoto antes de liberar o caixa local.

Não houve merge em main, deploy, migração, escrita em ganoh_production nem
alteração do Render. Consultas reais somente leitura, testes em bancos descartáveis
e código na branch
feature/windows-offline-ganoh-2026. Não distribuir cópia real do banco em GitHub.

PR: https://github.com/xitios660-ctrl/Ganoh1/pull/6
