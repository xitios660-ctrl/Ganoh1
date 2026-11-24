# Integração local de histórico — 23/11/2026

Status: implementado com fixtures; não é entrega final dos aplicativos PC/TV com
dados reais. PR #6 permanece rascunho. Produção e site não foram alterados.

## Incremento

- `desktop/local_api.py`: proprietário autenticado importa pacote cifrado por unidade;
  limite 40 MiB, corpo limitado antes do parsing, arquivo temporário somente com
  bytes cifrados e removido ao terminar, mutex contra importações simultâneas.
  Não aceita URI Mongo, caminho do disco ou backup integral do servidor. A carga
  é executada fora do event loop; checkpoint SQLCipher permite retomar reenviando
  o mesmo pacote. Consulta paginada preserva BSON/Decimal128; respostas no-store.
- `DesktopHistoryPanel.jsx` e `DesktopDemoPage.jsx`: painel do proprietário para
  importar/retomar e consultar vendas, despesas, clientes, estoque e estornos.
  Frase apagada do estado após cada tentativa, sem localStorage; valores históricos
  exibidos como strings exatas, sem soma ao caixa ou conversão monetária em float.
- `test_history_api.py`: autenticação/roles, reenvio, consulta, cifra, arquivo temporário,
  frase errada, unidade errada, limites e recusa de caminho/coleção privada.
- `DesktopHistoryPanel.test.jsx`: paginação por cursor, Decimal128 grande preservado,
  envio de pacote e limpeza da frase após perda de resposta.
- `windows_packaged_smoke.py`: exercita importação no executável empacotado e após
  nova reinstalação/reabertura, mantendo histórico schema 4 e fila de vendas anterior.

## Testes locais

- Desktop: 67 executados, 65 aprovados e 2 exclusivos Windows ignorados no Linux.
- React existente: 13 aprovados; novo painel: 2 aprovados.
- Build React desktop aprovado; compilação Python e diff sem erros.
- Smoke PyInstaller/NSIS exige CI Windows deste commit; não atribuir resultados
  antigos à nova rota de importação. Sem teste físico nas lojas.

## Bloqueios reais

IP Atlas solicitado foi liberado pelo proprietário e confirmado. Conexão TCP
continua recusada neste executor, também em teste direto a outro destino público;
HTTP via proxy funciona. Snapshot do executor: sem VPN e sem grants TCP; ferramenta
de alteração de ambiente não disponível. Política HTTP unrestricted não garante
conexão Mongo na porta 27017. Não contornar política com relay arbitrário nem abrir
Atlas para 0.0.0.0/0. Nenhum backup real foi capturado e nenhuma senha foi validada.

Precisamos executar captura e restauração em executor isolado com TCP permitido.
Credenciais disponibilizadas pelo proprietário não devem entrar em Git, artefato
público ou aplicativo. Não mudar senha dos usuários do site.

Continuam pendentes: backup e conferência reais, conciliação operacional, paridade
com as telas e regras originais, mudanças posteriores ao snapshot, central real
idempotente/hospedagem e consumo desses dados pelo Android TV. O painel novo da TV
continua apontando para homologação; não enviar demonstração como versão final.

## Chromium e correção do smoke Windows

`python -m desktop.tests.browser_history_smoke` aprovado com Chromium real: login
local, importação pela tela, valor Decimal128 exato, frase limpa, reload preservando
histórico, nenhuma nova operação na fila e nenhuma requisição externa. Tema continua
podendo guardar sua preferência; credenciais/histórico não entram no localStorage.
Screenshot de fixture inspecionada visualmente. Novo roteiro em browser_history_smoke.py.

A primeira CI f2f9ab1 falhou no smoke Windows por import do módulo backend fora do
sys.path ao executar o roteiro como arquivo. Corrigida inclusão explícita da raiz
no roteiro; o resultado Windows desta correção precisa ser validado novamente.
Regressões Linux/central/React do primeiro commit passaram. Não ocultar falha inicial.

Tentativa de preparar repositório privado para executor temporário de backup foi
recusada pelo GitHub: Resource not accessible by integration (createRepository).
Nenhum repositório foi criado, nenhuma credencial ou dado foi enviado ao GitHub.
Falta infraestrutura com acesso TCP e armazenamento privado para o backup real.

## Alternativa privada preparada

`ops/private-backup/backup.yml` é template inativo, fora de .github/workflows.
Só roda por workflow_dispatch em repo privado, revalida visibilidade pela API,
baixa código fixado por SHA, usa secrets, captura BSON e restaura em Mongo8 tmpfs
local. Só publica artefato cifrado após conferir a restauração; retenção 3 dias.
Nenhum deploy/site é afetado. README descreve custódia da chave, IP do runner,
revogação e possível consumo de cota Actions. YAML e Python embutido validados
sintaticamente; execução real ainda não realizada. Criação manual/acesso ao repo
privado foi solicitada ao proprietário, pois criação automática foi negada.

## CI corrigida validada — d38f8d1

- Regressão aprovada: https://github.com/xitios660-ctrl/Ganoh1/actions/runs/45091810090
  67 Windows; Linux 65+2 skips; 32 central; 15 data_bridge; 15 React; 2 Node;
  compilação desktop/gestor. O smoke de importação source Windows passou.
- Instalador aprovado: https://github.com/xitios660-ctrl/Ganoh1/actions/runs/45091810164
  PyInstaller/NSIS, importação via API empacotada, reinstalação/reabertura preservando
  schema4, histórico e fila anterior, desinstalação preservando chave/dados.
- Chromium real local aprovado com fixture. Não é teste físico Windows/TCL nem
  integração de produção. Nenhuma demonstração nova foi entregue como app final.
