# Executor privado GANOH — 24/11/2026

## O que avançou

Proprietário disponibilizou Ganohgostozin como repositório privado dedicado. API
GitHub confirmou private=true, viewerPermission=ADMIN, conteúdo existente e dois
workflows manuais. README e workflows anteriores foram inspecionados e preservados.
Não foi criado outro repo nem reutilizado projeto de terceiros.

Workflow adicional de fixtures criado no repo privado no commit
75910195cf8c5dd4f1df6fa9a74c4edd3e4fc63d, sem Secrets, sem Atlas e sem dados reais.
A fonte pública está fixada em a50e04525721d230b8ae5b3d9814cd51fe9b1ff7.
O arquivo de revisão em ops/private-backup/fixture-restore.yml NÃO é ativo aqui.
Somente o repo privado recebe esse workflow ativo. Não é deploy de produção.

## Ensaios executados

https://github.com/xitios660-ctrl/Ganohgostozin/actions/runs/45300890486 — success.

- 18 testes de captura BSON cifrada, snapshot, restauração isolada e unidade em
  MongoDB8 descartável, em tmpfs e com TTL desligado, aprovados.
- Novo teste SCRAM local real: usuário com read aceito pelo preflight; usuário
  com readWrite recusado. As senhas eram fixtures aleatórias do runner.
- Somente bancos de ensaio locais; nenhum documento real, secret ou Atlas foi usado.
- Container removido no encerramento; não houve publicação de backup/artifact real.
- Não é prova de rede/autenticação/snapshot/restauração do banco real nem teste físico.

README privado atualizado em 970846082ea33b5e342360782dfd7ce7993033a7 com evidência
do ensaio e as limitações. Execução privada pode consumir cota Actions; não foi
verificado saldo/franquia nem assumida gratuidade. A duração do job é limitada.

## Acesso real e condições pendentes

Consulta de metadados de usuários no Atlas Regex identificou UMA conta com função
única read em ganoh_production e scope único Cluster0. Não é necessário criar outro
usuário. A credencial administrativa previamente mostrada não será usada. Não foi
alterada conta, senha ou configuração de produção nesta etapa.

A integração consegue escrever workflows e disparar o ensaio privado, mas recebe
HTTP403 ao consultar Secrets, chave pública de Secrets e configuração do Actions.
Não presumir que Secrets existem ou faltam. Não tentar divulgar/extrair seus valores.
O proprietário precisa cadastrá-los ou confirmar o cadastro no GitHub privado:
GANOH_SOURCE_USERNAME, GANOH_SOURCE_PASSWORD, GANOH_BACKUP_PHRASE.
Frase de recuperação deve ter custódia independente; nunca em commit/chat/log.

Ainda falta confirmação independente, no próprio ambiente do Render, de apenas
host e DB_NAME efetivamente usados. Correlação de logs/coleções não prova MONGO_URL.
Essa confirmação, o cadastro/custódia dos Secrets, cota/custo e liberação do IP /32
atual do runner são condições antes de executar backup real. Foram solicitadas
confirmações ao proprietário sem pedir valores secretos.

## Próxima ação

Quando essas condições forem atendidas, disparar uma única execução supervisionada
do workflow de backup real já existente, com VALIDAR_BACKUP. Autorizar somente o
IP do job atual, temporário, sem retirar IPs das lojas e nunca 0.0.0.0/0. Não usar
IP do ensaio anterior como se fosse permanente. Não iniciar job sem Secrets prontos.

Só após sucesso de snapshot e restauração/hash/BSON/índices poderá ser derivado
pacote unitário. Backup cifrado validado e chave precisam de custódia fora do
artefato de 3 dias. Depois, revogar acessos temporários com confirmação. Nenhum
resultado real é anunciado antecipadamente.

Faltam conciliação financeira/estoque e dados sem unidade, delta pós-snapshot,
integração central HTTPS e atualização dos apps com dados reais. Windows permanece
bloqueado para baseline não conciliado; TV não deve mostrar fixtures como reais.
PR #6 segue rascunho. Ganoh1/main, Render atual e registros de produção intactos.
