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
- Workflow Android TV disparado pelo PR (sem mudanças Android): a primeira
  execução falhou ao baixar dependência Maven dos testes; repetição em andamento.
  Não usar esse resultado como aprovação Android deste commit.

## Limitações que impedem entrega final

O site informado `https://ganoh-minjuin.onrender.com/` respondeu HTTP 200. Não há
origem Mongo confirmada nem backup dos dados reais neste incremento. O conector
Render exige confirmar o workspace antes de consultar os serviços; está pendente
confirmar “Min's workspace” na conexão Minjuin. Nenhuma configuração foi alterada.

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
alteração do Render. Apenas testes em bancos descartáveis e código na branch
feature/windows-offline-ganoh-2026. Não distribuir cópia real do banco em GitHub.

PR: https://github.com/xitios660-ctrl/Ganoh1/pull/6
