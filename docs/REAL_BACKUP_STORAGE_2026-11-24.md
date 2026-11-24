# Backup real — confirmação de origem e bloqueio de armazenamento

## Confirmações novas

O proprietário consultou os campos do ambiente no Render e informou DB_NAME e
host correspondentes a ganoh_production/Cluster0 esperado. Trata-se de confirmação
pelo proprietário na interface do serviço, não de leitura de MONGO_URL pelo conector.
Nenhum valor de senha ou URI autenticada deve aparecer em Git/relatório/log.
A credencial de serviço exposta na conversa não foi usada no backup; sua rotação
precisa ser coordenada com Render para preservar o site ativo.

Usuário read restrito já verificado no Atlas; proprietário cadastrou três Secrets.
O workflow confirmou que GANOH_SOURCE_USERNAME, GANOH_SOURCE_PASSWORD e
GANOH_BACKUP_PHRASE estão presentes e que a frase tem tamanho permitido. Não
expôs valores, não confirmou senha correta nem autenticação real no banco.

## Workflow privado supervisionado

Commit privado 48e7c200331061b6799de0275bc87d813ed6fdf1 adiciona confirmação de
origem, checagem prévia de Secrets e artefato privado do IP do runner atual, com
retenção de 1 dia. Backup cifrado mantém 3 dias, só depois de restore validado.
O metadado é publicado antes de conectar à origem: falha de armazenamento para
antes de copiar dados. Autenticação inválida não é repetida 60 vezes.
YAML e scripts Python embutidos foram validados sintaticamente antes da execução.
O core de backup permanece fixado em a50e045, previamente ensaiado com fixtures.

https://github.com/xitios660-ctrl/Ganohgostozin/actions/runs/45399508258
Tentativa 1: failure por Artifact storage quota has been hit.
Tentativa 2 após limpeza: mesma falha; GitHub informa recálculo a cada 6–12 horas.
Em ambas: Secrets present/privacidade aprovados; etapa de captura e restauração
SKIPPED. Nenhum snapshot, restore ou artefato real foi produzido. Não afirmar que
esta falha significa perda de dados ou senha inválida. Não houve conexão ao Atlas
pelo job, alteração no serviço Render nem escrita em ganoh_production.

## Limpeza limitada realizada

Inventário Ganoh1 mostrou nove instaladores antigos de demonstração, sem dados
reais. Antes de remover, cada artefato foi consultado pela API: nome exato
GANOH-Windows-DEMO-UNSIGNED e head_branch feature/windows-offline-ganoh-2026.

Removidos somente IDs 14738312430, 14626940982, 14479901877, 14477964316,
14387553487, 14385298998 e 14386295078, total aproximado 837,5 MiB. Esses downloads
antigos deixam de existir; referências históricas antigas podem apontar para
artefatos removidos. Seus commits/código e logs foram preservados para reconstrução.
Preservados os dois mais recentes: 14781264195 (run45091810164) e 14739512840
(run44985490420). Nenhum artefato de backup real, banco, arquivo fonte ou outro
projeto foi removido. A remoção não comprova recálculo imediato da cota.

## Próxima ação

Após o recálculo, executar uma nova verificação supervisionada do armazenamento.
Não criar tentativas recorrentes ou custos extras sem necessidade. Só após o
metadado ser publicado haverá runner ativo/IP a autorizar temporariamente /32.
Preservar regras das lojas, nunca 0.0.0.0/0. Não solicitar liberar IP de job morto.

Depois: autenticação read, snapshot BSON completo, restauração local descartável,
BSON/índices/hash, custódia cifrada externa com chave independente, pacotes por
unidade, conciliação e delta. Windows e TV continuam não homologados com dados reais.
PR #6 rascunho; main do Ganoh1 e produção intactas. Não implantar nesta etapa.
