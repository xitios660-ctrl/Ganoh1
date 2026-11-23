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
2. Revisar a revisão fixa d38f8d1 do código, workflow e prazo de retenção (3 dias).
3. Cadastrar secretos GANOH_SOURCE_USERNAME, GANOH_SOURCE_PASSWORD e uma frase de
   recuperação forte GANOH_BACKUP_PHRASE. Guardar a frase separadamente em custódia
   do proprietário; secrets do GitHub não permitem recuperar seu valor depois.
4. Usar usuário read somente em ganoh_production/Cluster0. O usuário administrativo
   autorizado pelo proprietário só deve ser usado para leitura; o script chama
   exclusivamente ping e capture na origem. Não muda senha/configuração do site.
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
