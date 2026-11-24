# Executor privado de backup — proposta ainda não executada

Este YAML é um template inativo. Não copiar para workflows do repositório público.
Objetivo: oferecer executor temporário fora da rede que recusa TCP Mongo aqui,
sem precisar de computador do proprietário, sem deploy ou mudança no site.

Requer repositório privado do proprietário, conexão GitHub com acesso a esse repo,
GitHub Actions habilitado e cota disponível (execução pode consumir minutos pagos).
Não foi possível criar o repo automaticamente: integração recusou createRepository.

Antes de execução real:

1. Verificar isPrivate por API e visibilidade/revisores de acesso. O template recusa
   repo público tanto por condição quanto consulta autenticada. Nunca colocar
   dados, credenciais ou chave em arquivos Git; artefatos exigem repo privado.
2. Revisar código/workflow fixado em `a50e04525721d230b8ae5b3d9814cd51fe9b1ff7`, incluindo preflight.py.
   Não usar referência móvel. Revisar retenção (3 dias).
3. Cadastrar secretos GANOH_SOURCE_USERNAME, GANOH_SOURCE_PASSWORD e uma frase de
   recuperação forte GANOH_BACKUP_PHRASE. Guardar a frase separadamente em custódia
   do proprietário; secrets do GitHub não permitem recuperar seu valor depois.
4. Usar usuário dedicado com SOMENTE read em ganoh_production, restrito a Cluster0.
   Conferir roles/scopes pelo inventário Atlas antes de executar. O preflight
   connectionStatus verifica a identidade real e recusa funções adicionais, inclusive
   administrador ou readWrite, antes da captura. Não altera usuário do site.
   Confirmar previamente, por inspeção segura no Render, somente host e nome do
   banco efetivamente usados, sem mostrar MONGO_URL autenticada. A evidência dos
   logs e das consultas Atlas não substitui essa confirmação independente.
5. Executar manualmente. Autorizar somente IP /32 mostrado pelo runner no Atlas,
   com expiração curta; ele pode mudar entre execuções. Tentativas têm prazo limitado.
6. Não entregar arquivo se captura ou restauração falhar. Conferir recibo/hash,
   baixar backup cifrado para armazenamento privado, testar custódia da chave,
   remover secrets/artefato e revogar o acesso/IP após validar a cópia.

O Mongo de restauração roda em tmpfs isolado com TTL desligado. Nunca passa a URI
remota como destino de restauração. Dados reais em memória do runner são apagados
com o container; backup publicado no artefato é cifrado e somente após validar.
TLS permanece ativo na conexão Atlas. Não imprime senha, URI autenticada ou registros.

Ainda não foi executado contra dados reais nem validado nesse novo executor.
Não é central de sincronização nem integra o Android TV automaticamente. Completar
histórico não substitui conciliação de saldos/alterações posteriores ao snapshot.

## Executor privado disponível — 24/11/2026

O proprietário escolheu `xitios660-ctrl/Ganohgostozin`. Privacidade e acesso ADMIN
confirmados pela API; dois workflows já existentes foram preservados. Foi adicionado
`fixture-restore.yml` exclusivamente para ensaio sem Secrets ou conexão de produção.
Cópia deste novo roteiro fica aqui como template inativo para revisão.

Ensaio privado aprovado em https://github.com/xitios660-ctrl/Ganohgostozin/actions/runs/45300890486 :
18 testes data_bridge em Mongo8 descartável e teste SCRAM local real aceitando read
recusando readWrite. Não confundir com autenticação/restauração de produção.
O Mongo descartável foi removido; nenhum artefato real foi publicado.

A conta read restrita exigida foi identificada no Atlas por consulta de metadados.
Os valores dos Secrets não foram lidos. A API de Secrets e sua chave pública retornam
403 à integração, portanto o proprietário deve configurar os três nomes na interface
privada. Não é possível afirmar se já foram cadastrados. Confirmação independente
de host/DB efetivo do Render e custódia da chave ainda são condições de execução real.
