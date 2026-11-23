# Preparação do backup real — auditoria de continuação de 23/11/2026

Não concluído. Somente consultas e alterações na branch de desenvolvimento.
Nenhuma alteração de configuração, usuário ou registro em produção, nenhum deploy,
merge, secret novo, repositório novo ou execução de backup real nesta etapa.

## Evidências verificadas novamente

- Comentário técnico lido na íntegra:
  https://github.com/xitios660-ctrl/Ganoh1/pull/6#issuecomment-7089745650
- PR #6 aberto, rascunho, sem merge, head feature/windows-offline-ganoh-2026.
- Regressão e instalador d38f8d1: ambos completed/success na API GitHub:
  https://github.com/xitios660-ctrl/Ganoh1/actions/runs/45091810090
  https://github.com/xitios660-ctrl/Ganoh1/actions/runs/45091810164
  Fixtures: 67 Windows; Linux 65+2 skips; 32 central; 15 data_bridge; 15 React;
  2 Node/builds; PyInstaller/NSIS e histórico preservado após reinstalação.
- Inventário de usuários no Atlas Regex consultado somente leitura: nenhum usuário
  com exatamente read em ganoh_production, sem função adicional, restrito a Cluster0.
  Não utilizar credencial administrativa disponibilizada anteriormente nesta etapa.
- GitHub lista repositórios privados acessíveis, com viewerPermission ADMIN.
  Nenhum foi aberto, alterado ou reutilizado como executor de backup.
  Ganoh-private-validation NÃO foi localizado com a credencial atual. Isso não
  distingue ausência de repo de falta de acesso da integração; proprietário deve
  confirmar a criação e concessão de acesso. ADMIN em outros repos não prova
  permissão para criar novo repo, gravar secrets ou executar workflows nesse alvo.

## O que existe e funciona em ambiente isolado

Biblioteca de snapshot BSON sem corte de datas, cifra AES-GCM, manifesto, hashes,
publicação sem sobrescrita e restore somente em Mongo loopback vazio de ensaio.
Pacote por unidade exige comprovante de restauração do arquivo exato, preserva
estornos/dívidas e recusa escopo ausente, coleção desconhecida e mistura aninhada.

Windows: cache SQLCipher, importação por proprietário, paginação/retomada, bloqueio
financeiro enquanto baseline não conciliado, persistência/reinstalação e outbox.
Central autenticada e idempotente funciona somente em ganoh_sync_test_*.
TV consulta essa central em HTTPS, com tv:read e unidades autorizadas. Não existe
integração comercial com banco real nem paridade completa do sistema original.

## O que foi comprovado com dados reais

As auditorias anteriores consultaram ganoh_production no Atlas Regex: 22 coleções,
duas unidades e registros até 21/11. Contagens do comentário são fotografias em
instantes diferentes, não precisam permanecer iguais. Não copiar registros ou
contagens comerciais para este repo público. prazo_debts vazio não prova ausência
de dívida: conciliar pedidos, históricos, recebimentos parciais e estornos.

Nenhum backup consistente, restauração, saldo inicial ou delta real foi validado.
A URI efetiva usada pelo serviço Render NÃO foi confirmada independentemente.
Logs/dados compatíveis são evidência, não prova da variável secreta MONGO_URL.
É necessário conferir apenas host e DB_NAME no ambiente do serviço por canal
seguro, sem importar server.py (pode executar rotinas) nem divulgar credenciais.

## Ambiente privado proposto e condições de execução

GitHub Actions Ubuntu em repo privado dedicado Ganoh-private-validation, ainda
indisponível para esta integração. Não reutilizar projetos privados existentes nem
instalar workflow no Ganoh1 público. O template está em ops/private-backup/backup.yml,
fora da pasta ativa .github/workflows. Revalida privacidade via API, dispara só
manualmente, tem duração máxima de 15 minutos e artefato cifrado por 3 dias.
Fonte fixada em a50e04525721d230b8ae5b3d9814cd51fe9b1ff7, incluindo a nova verificação
de identidade autenticada. Mongo8 local descartável em tmpfs é destino do restore.

Antes de qualquer execução real:

1. Proprietário confirmar/criar repo privado e dar acesso à conexão GitHub.
2. Conferir permissões reais de contents/workflows, Secrets e Actions; confirmar
   Actions habilitado e orçamento/cota. Primeiro ensaiar o executor com fixtures.
3. Confirmar host e banco efetivos do Render por inspeção segura sem mudar serviço.
4. Criar usuário dedicado somente read em ganoh_production, scope Cluster0, após
   estabelecer custódia segura. A criação não foi realizada. Não alterar usuários
   do site. Secrets: GANOH_SOURCE_USERNAME, GANOH_SOURCE_PASSWORD, GANOH_BACKUP_PHRASE.
   Guardar frase de recuperação separadamente; Secrets não é cópia recuperável.
5. Na execução, liberar somente IP atual /32 do runner, com expiração curta.
   Nunca 0.0.0.0/0 nem substituir entradas das lojas. Revalidar após troca de runner.
6. Capturar snapshot, restaurar e conferir BSON/contagens/índices/manifesto/hash.
   Não publicar artefato se falhar. Transferir cópia cifrada validada para custódia
   privada independente ANTES de expirar o artefato. Testar recuperação da chave.
7. Revogar usuário/IP, remover secrets temporários/artefatos conforme retenção,
   registrando confirmação. Não presumir que o conector oferece remoção automática.

## Ajuste implementado e validação desta etapa

- backend/data_bridge/preflight.py: consulta connectionStatus (leitura), verifica
  identidade efetivamente autenticada e exige somente read em ganoh_production.
  Não basta chamar ping com conta admin. Funções adicionais/admin/readWrite são
  recusadas antes de capture; escopo Cluster0 também exige inventário Atlas.
- backend/data_bridge/tests/test_preflight.py: três testes aprovados, sem acesso
  a produção: função mínima aceita; identidades/funções indevidas recusadas; erro
  remoto não revela corpo sensível. Testes usam mocks; teste de autenticação real
  no executor privado ainda é necessário.
- ops/private-backup/backup.yml e README.md: passam a exigir conta dedicada,
  removem a alternativa administrativa e fixam commit que contém o preflight.
  YAML carregado e programa Python embutido compilado sintaticamente, sem executar.

## Custos e testes restantes

Não foi contratado recurso nem iniciado job privado. GitHub Actions e armazenamento
em repo privado podem consumir franquia ou gerar cobrança conforme plano. Saldo,
limites e autorização de custo devem ser conferidos na conta antes de disparar.
Não há estimativa monetária comprovada; não tratar como garantidamente gratuito.
Hospedagem central HTTPS e armazenamento privado durável ainda precisam de escolha
e orçamento próprios; executor de backup não é servidor permanente dos apps.

Faltam: ensaio completo do executor privado com fixtures, autenticação read real,
snapshot/restauração reais, conferência financeira por unidade e deduplicação entre
pedidos/histórico, classificação de dados sem unidade, delta após snapshot,
idempotência na integração legada, sincronização HTTPS de homologação, revogação,
recuperação/atualização e testes físicos Win10/11/dois PCs/TCL. Não liberar caixa
nem apresentar valores de fixtures como reais na TV.

Próxima ação concreta: obter acesso ao repo privado dedicado. Depois preparar
somente o ensaio com fixtures, comprovar permissões/custos/custódia e executar o
backup real quando todos os requisitos acima estiverem atendidos.

## Regressão da preparação a4dca25

https://github.com/xitios660-ctrl/Ganoh1/actions/runs/45099435939 — completed/success.
67 testes desktop Windows; Linux 65+2 skips; 32 central; 18 data_bridge (incluindo
os 3 novos testes de permissões); 15 React; 2 Node e builds desktop/gestor.
Autenticação read contra o Atlas e ensaio do executor privado não estão incluídos.
Não houve novo build NSIS necessário nesta alteração de preflight/template; a
referência validada do instalador é d38f8d1, não uma homologação com dados reais.
