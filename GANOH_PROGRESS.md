# GANOH — Continuidade do trabalho

## Etapa atual
Etapa 1 em andamento — incrementos 1A, 1B.1, 1B.2, 1B.3a, 1B.3a.1–1B.3a.8 (idempotência persistente opcional no pagamento parcial) implementados e validados.
Etapa 0 — auditoria de código e navegação pública concluída em 22/09/2026.
Validação autenticada, reconciliação do banco real e confirmação dos segredos de implantação continuam pendentes; não declarar produção validada.
Próximo incremento: 1B.3b, transação da quitação e teste concorrente em Mongo descartável. Não avançar à etapa 2 enquanto os gates financeiros estiverem pendentes.

## Retomada obrigatória
1. Ler este arquivo e os commits da branch ganoh/staged-audit e da main.
2. Conferir diff e estado do código antes de editar. Não refazer correções existentes.
3. Testar sem startup conectado a banco real, sem envio de WhatsApp e sem lançamentos reais.
4. Atualizar este registro e criar commit após cada incremento validado.
5. NÃO enviar a main ou fazer merge/deploy antes das etapas 1–11 e do checklist da etapa 12.
6. Se automações antigas continuarem, devem respeitar esta branch e este plano; não publicar correções isoladas na main.

## Base, rollback e último commit
- Base de código auditada: def13cf952811907329e0da79544699b2783ee37.
- Último commit anterior a esta atualização / ponto de rollback: 5d5e57cf5c41f35dc1cc6a8ad081363ca59265c0 (pagamento parcial calculado em centavos).
- O commit que contém este diagnóstico é obtido por git log -1 -- GANOH_PROGRESS.md. Um arquivo não pode conter o próprio SHA final.
- Rollback de código: conservar a base e reverter somente commits novos, sem apagar dados ou forçar referências.
- Rollback de banco ainda NÃO existe como backup verificado. Não executar migração ou reparação de dados.
- Main e branch de trabalho foram conferidas na retomada; main continuava na base.
- Não foi encontrado AGENTS.md na árvore remota auditada nem no workspace.
- Checkout local é parcial, majoritariamente não rastreado: não usar git add . nem enviar o diretório inteiro.
- Comparação de blobs locais com árvore remota: diferenças de newline em vários arquivos; diferença substantiva em frontend/src/index.css. CSS remoto foi consultado separadamente. Reobter fontes exatas antes do build final.

## Arquivos alterados na auditoria (etapa 0)
Somente GANOH_PROGRESS.md nessa etapa. Os incrementos posteriores de código estão discriminados abaixo. Nenhuma configuração de produção, dado ou saldo alterado.
Reprodutor temporário fora do repositório: audit_reproduce.py; usa coleções fictícias e mocks.

## Arquitetura inventariada
| Área | Implementação atual | Observação |
| --- | --- | --- |
| Frontend | React 19, React Router 7, CRA/CRACO, Tailwind, Radix, Recharts, Framer Motion, Three | frontend/src/App.js centraliza rotas; KitchenPage.js e GestorPage.js concentram operações |
| Backend | Python/FastAPI, Pydantic, Motor/PyMongo, HTTPX | backend/server.py com cerca de 6,4 mil linhas e routers adicionais |
| Banco | MongoDB via MONGO_URL e DB_NAME | sem acesso direto/backup do banco real nesta auditoria |
| API | prefixo /api; frontend usa REACT_APP_BACKEND_URL em build | destino incorporado ao JavaScript publicado |
| Caixa | get_today_cash, get_cash_drawer, gráficos do gestor, routers/cash.py e relatórios | múltiplas implementações; não há fonte financeira única |
| Clientes/dívidas | prazo_customers, orders com payment_method=prazo, registros de pagamentos | loja e identidade ainda inconsistentes em rotas antigas |
| Pagamentos | orders, pix_adjustments, prazo_payments, prazo_partial_payments, cash_credit_topups | UUID gerado por requisição não é chave de idempotência |
| Auditoria | histórico de prazo e metadados parciais de operações | não há trilha uniforme com funcionário e antes/depois em todas as operações |
| WhatsApp | proxy no server.py; opção Green API ou Node/Baileys | já existe frontend/src/components/gestor/WhatsAppTab.js; reaproveitar |
| Baileys | whatsapp/server.mjs, auth.mjs; Node >=22, versão 7.0.0-rc14 | sessão criptografada em Mongo; não partir do zero |
| Jobs | APScheduler no processo FastAPI | auto-ready a cada minuto; relatórios 14h e 22h America/Sao_Paulo |
| Implantação | Docker multi-stage + scripts/start_render.py + backend/render_app.py | API e Node no mesmo contêiner, Node em loopback |
| Migração | scripts/migrate_mongo.py | cópia para destino vazio, preserva BSON/índices, compara contagem/hash; exige origem pausada |

### Rotas e duplicações
Foram identificados 22 pares método/caminho repetidos no app carregado, incluindo 18 de caixa/prazo.
Os handlers do monólito são registrados antes dos routers; o comentário de que os novos routers teriam prioridade é enganoso. Verificar a rota efetivamente atendida em cada teste.
Corrigir apenas um arquivo duplicado pode não mudar o comportamento real.
Routers auth/admin/whatsapp existem, mas não são incluídos pelo trecho final do monólito; conferir uso antes de modificar.

## Produção observada — diferença importante
- O usuário confirmou https://ganoh.onrender.com; este endereço EXISTE e foi aberto no navegador.
- Serviço estático ganoh: srv-dapbpslbedkc738a63n0, repo Ganoh1, branch main, autoDeploy=yes, build frontend via npm ci e npm run build; publish frontend/build.
- Último deploy observado do estático: def13cf, live. Logo, commits anteriores em main dispararam publicação automática do frontend, mesmo sem deploy manual.
- Bundle observado: /static/js/main.380a58ba.js. Inspeção do artefato público encontrou https://charts-3.emergent.host e /api como destino.
- A UI do Render ainda depende do backend Emergent. NÃO afirmar que dados foram migrados ou que correções de backend do GitHub estão em produção.
- Serviço web separado Ganoh1: srv-daoufnrtqb8s73elp9vg, https://ganoh1.onrender.com, Docker free, autoDeploy=no; último deploy observado 351d1a7.
- Não renomear/criar serviços agora. Confirmar topologia final e banco antes da etapa 12.
- Homepage e navegação interna até /runner carregaram cardápio, categorias e preços.
- Ao recarregar /runner apareceu “Not Found”. Falta de fallback SPA no serviço estático é hipótese forte; configuração de rewrites precisa ser inspecionada.
- Nenhum login privado foi realizado nesta auditoria; não abrir cozinha autenticada indiscriminadamente: GET /orders/{store} pode arquivar pedidos antigos.
- Limite temporário de uso interrompeu uma leitura terminal posterior; essa chamada não foi executada. Trabalho retomado sem repetir a auditoria inteira.

## Caixa — causas e riscos encontrados
### Reproduzidos com dados fictícios no código auditado
1. add_pix_adjustment: duas chamadas com o mesmo PIX de R$100 criaram dois registros e total R$200. Falta chave estável do cliente e deduplicação atômica.
2. pay_all_prazo_customer: primeira chamada quitou 1 pedido; segunda quitou 0. Mesmo assim foram criados dois recebimentos de R$100 (total R$200). insert_one é incondicional após update_many.
Esses defeitos podem inflar o caixa. Ainda NÃO provam quais registros reais originaram a divergência relatada.

### Confirmados por leitura, exigem testes específicos
- create_order gera novo UUID e sync_offline_orders chama create_order para cada item sem deduplicar offline_id. Retry/offline/duas abas podem gerar pedidos repetidos.
- PIX manual e vendas manuais sem identificador estável e sem índice único da operação.
- Quitação total usa nome sem loja, escolhe loja do primeiro pedido e aceita valor informado sem calcular somente saldo restante.
- Abatimento/crédito alteram múltiplos documentos sequencialmente; risco de concorrência e gravação parcial; nenhuma transação financeira Mongo observada.
- Saldo de gaveta é cumulativo desde last_reset_at; não é automaticamente saldo do turno. Resumo diário e faturamento têm semânticas diferentes.
- Drawer soma dinheiro de orders + prazo_payments + prazo_partial_payments + cash_credit_topups menos saídas. Reenvio de qualquer gravação pode aumentar o saldo.
- get_today_cash exclui prazo; dashboard inclui pedidos a prazo no total. Relatórios usam cálculos próprios e não incluem exatamente os mesmos componentes.
- Filtragem temporal: helpers recentes corrigem offsets em alguns caminhos; gráficos/relatórios ainda comparam strings ISO e limites diferentes.
- Consultas usam to_list com limites antes da filtragem em Python; resultados podem ser incompletos conforme histórico cresce.
- Valores são float. Definir centavos/Decimal na camada de cálculo sem converter silenciosamente dados históricos.
- UI KitchenPage exibe current_balance e totais vindos da API; não foi encontrado nesse trecho acréscimo visual repetido ao atualizar. PIX manual é POST explícito, sem bloqueio de envio em andamento.
- Não apagar duplicados históricos automaticamente; reconciliação precisa de evidência e trilha, preservando valores originais.

## Tema
- ThemeProvider central usa classe dark no html, chave ganoh_theme_user e chave legada ganoh_theme.
- Alternância depende de transitionend da animação; não há fallback/limpeza completa do listener no caminho revisado.
- A chave legada é escrita, mas não é lida como fallback, apesar do comentário.
- Tema escuro foi ativado no cardápio. Reload direto falhou em Not Found, impedindo validar o fluxo solicitado.
- Voltando pela homepage e navegando internamente, o botão “Mudar para tema claro” confirmou que a preferência escura persistiu.
- Foi acionado retorno ao claro. Fluxo claro→reload→claro ainda não foi validado.
- CSS cinemático contém cores fixas e exceções próprias; existem variáveis de tema em index.css. Não redesenhar.
- Pendentes: mobile/desktop, gráficos/tabelas/cards autenticados, reduced motion e navegação direta.

## Autenticação, permissões e logs
- Gestor: HTTP Basic no backend com comparação segura de credenciais de ambiente.
- Tenants: login separado com SHA-256 simples de senha; não é hash de senha apropriado com salt/custo.
- verify_whatsapp_manager aceita credencial de tenant ou gestor; cadastro público de tenant e papéis precisam ser revistos antes de liberar configuração sensível.
- UI armazena credenciais Basic codificadas em base64 no localStorage; isso não é criptografia.
- Gate de equipe usa senha fixa no frontend/sessionStorage; não constitui autorização no backend.
- PIX manual, várias operações de cozinha e crédito não têm verificação de gestor equivalente.
- Foram encontrados defaults de credenciais/provedor no código. Não copiar valores neste arquivo; tratar como expostos e planejar rotação com impacto avaliado.
- Exceptions de HTTPX são registradas/retornadas como str(e) em alguns caminhos; URL do provedor pode conter token. Redigir logs/erros antes da ativação.
- Há proteções recentes válidas de administração; preservá-las e testar antes de modificar auth.

## WhatsApp, comprovantes, IA e fechamentos
- Área WhatsApp existente: status, QR, conectar, listar grupos e selecionar destino/link. Faltam número, desconectar, última conexão, eventos/comprovantes/erros estruturados.
- Proxy de status/QR/configuração exige autenticação. Serviço Node exige token interno e escuta somente 127.0.0.1.
- Credenciais Baileys criptografadas AES-256-GCM no Mongo (baileys_auth), com chave de ambiente; não dependem de filesystem efêmero.
- Lease Mongo (baileys_locks) evita duas instâncias; backoff de reconexão, tratamento de logout/badSession e conflito já existem.
- Requer mesma DB_NAME/MONGO_URL/WHATSAPP_SESSION_KEY em reinícios. Rotacionar chave sem migração invalida leitura das sessões.
- Testes atuais de persistência usam Map e reinicializam adapter; NÃO simulam processo real, queda de rede, deploy Render ou pareamento verdadeiro.
- Logout/badSession apagam a coleção de auth; revisar escopo/erro antes de ampliar para múltiplas sessões.
- Não há listener de mensagens recebidas/comprovantes no server.mjs; syncFullHistory=false e getMessage retorna undefined.
- Seleção de destino admite grupos e números individuais. Envio permite qualquer JID válido, sem allowlist do grupo oficial; Runner possui grupo separado. Requisito de grupo único ainda não satisfeito.
- OCR de comprovantes já existe no fluxo de pedidos com emergentintegrations/EMERGENT_LLM_KEY. Há autoaprovação por análise; não há deduplicação global por hash/E2E ID observada.
- Reenvio de comprovante cria nova tarefa asyncio; concorrência/notificação usa checagem não atômica. Não ativar lançamentos por WhatsApp antes de ledger/idempotência/revisão.
- OPENAI_API_KEY e assistente com funções financeiras seguras ainda não implementados no fluxo auditado.
- Relatórios 14h/22h já existem, mas calculam totais independentemente; não há chave persistente data+turno+unidade nem outbox para envio.
- Scheduler local não garante exclusão entre instâncias/restarts. Relatório 22h é acumulado do dia, não somente segundo turno.
- Mensagens de PIX e cobranças têm outros caminhos automáticos/manuais. Separar consulta autorizada, alertas técnicos e fechamento; não presumir que desativar um job bloqueia todo envio.
- WHATSAPP_SEND_ENABLED bloqueia Node, mas não todos os caminhos Green API do backend.

## Ambiente e Render
Nomes inventariados (valores secretos não inspecionados/publicados):
MONGO_URL, DB_NAME, GESTOR_USERNAME, GESTOR_PASSWORD, PRAZO_PASSWORD, CLEAR_DATA_PASSWORD,
CORS_ORIGINS, REACT_APP_BACKEND_URL, MIGRATION_PENDING, SCHEDULER_ENABLED, SYNC_GESTOR_PASSWORD,
WHATSAPP_PROVIDER, WHATSAPP_INTERNAL_TOKEN, WHATSAPP_SESSION_KEY, WHATSAPP_SEND_ENABLED,
WHATSAPP_GROUP_ID, WHATSAPP_GROUP_RUNNER, GREEN_API_URL, GREEN_API_INSTANCE, GREEN_API_TOKEN,
EMERGENT_LLM_KEY, RESEND_API_KEY, SENDER_EMAIL, PORT.
OPENAI_API_KEY será necessária na etapa 7.
render.yaml configura ganoh1, Docker free, manutenção ativa e jobs/envio desativados por padrão.
render_app exige configuração de banco/senhas ao sair da manutenção e serve SPA no mesmo domínio; essa proteção não é aplicada ao serviço estático ganoh.
Preservar manutenção até migração validada se a topologia final passar a usar o backend Render.
Não há prova de migração concluída, de backup recuperável ou de equivalência dos saldos reais.

## Testes executados e resultados
- 78 testes Python passaram, 6 avisos de depreciação, na seleção local segura:
  test_admin_financial_security.py, test_payment_method_idempotency.py,
  test_cash_input_validation.py, test_cash_legacy_payments.py,
  test_render_deployment.py, test_prazo_credit_scope.py, test_prazo_credit_amount.py.
- 2 testes Node passaram: criptografia/adulteração e reabertura do adapter Mongo fictício.
- Duas reproduções financeiras acima confirmaram duplicação (defeitos ainda não corrigidos nesta etapa).
- Registro de rotas em memória confirmou 22 duplicações.
- Navegação pública e tema parcial conforme seção de produção.
- Render informa build frontend da base como live; não foi feito novo build local completo com snapshot exato.
- O repositório remoto contém muitos testes históricos ausentes da cópia parcial. Não executar suite indiscriminadamente: revisar URLs/credenciais e mutações primeiro.
- Nenhum teste em banco real, envio WhatsApp, QR pareado, OpenAI pago ou lançamento financeiro real executado.

## Decisões técnicas para etapa 1
- Começar pelo PIX manual: operation_id estável gerado antes do envio, reaproveitado em retry; inserção atômica no banco e replay retornando resultado original; payload conflitante deve falhar.
- Testar R$100, refresh/leitura, repetição, concorrência e novo processo com persistência; identificador novo representa operação nova legítima.
- UUID novo no servidor a cada chamada NÃO resolve replay.
- Definir compatibilidade com clientes antigos e payload antes de tornar o campo obrigatório; não derrubar clientes ativos no Emergent.
- Escolher incrementalmente fonte única de cálculo, mantendo distinção entre faturamento, recebimentos e dinheiro em gaveta.
- Não fabricar ledger histórico nem recalcular/sobrescrever saldos reais. Acrescentar rastreabilidade sem destruir documentos.
- Avaliar suporte real a transações do Mongo e estratégia de índices sem bloquear/alterar produção nesta fase.

## Pendências por etapa
0: comparação autenticada e configuração efetiva dos segredos pendentes; auditoria estática/pública registrada.
1: implementar e testar idempotência, cálculo central e auditoria, incluindo quitação total e offline.
2: corrigir fallback de navegação/tema e testar ambos temas em todas as páginas.
3: completar WhatsAppTab existente com autorização real e eventos.
4: validar sessão persistente com restart de processo/Render sem envio.
5: impor grupo oficial salvo e autorizado em todos os caminhos.
6: entrada de documentos, hash/transação, revisão e idempotência financeira.
7–8: OpenAI por funções de leitura, sem autoridade para inventar ou mudar valores.
9: fechamento único 14h/22h com cálculo central e controle durável de envio incerto.
10: sanitização de logs, credenciais e permissões.
11: regressão completa em ambiente isolado, incluindo frontend/build.
12: somente após os gates; confirmar banco/backup/migração, destino da API, SPA, ambiente e rollback, publicar e validar sem movimentar dados reais.

## Próxima ação recomendada
Retomar a etapa 1 pelo incremento 1B.3b de quitação total em ganoh/staged-audit; ler os registros 1A, 1B.1, 1B.2 e 1B.3a abaixo.
Antes de qualquer deploy, resolver a dependência da API Emergent e obter reconciliação/backup autenticados.

## Incremento 1A — PIX manual (22/09/2026)
### Concluído
- operation_id UUID opcional no contrato da API para preservar clientes legados.
- Novos clientes KitchenPage sempre enviam o UUID; chave determinística em _id com loja usa unicidade nativa do Mongo.
- Duplicidade atômica retorna o registro original. Mesma chave com valor/descrição diferentes retorna 409.
- Replay de PIX removido não recria entrada. ID/timestamp originais preservados.
- source=manual_pix e payment_method=pix adicionados aos novos registros identificados.
- Frontend salva operação em sessionStorage ANTES de enviar; sobrevive a reload da aba, conserva chave em erro e recupera formulário.
- Bloqueio síncrono de clique duplo + botão de envio ocupado.
- Resposta de servidor antigo sem operation_id bloqueia novas tentativas daquela operação para exigir conferência.
- Falha de armazenamento impede envio; tentativa pendente com payload diferente também bloqueada.

### Arquivos alterados no incremento
- backend/server.py
- backend/tests/test_pix_operation_idempotency.py (novo)
- frontend/src/pages/KitchenPage.js
- frontend/src/services/pixOperation.js (novo)
- frontend/src/services/pixOperation.test.js (novo)
- GANOH_PROGRESS.md

### Testes e resultados
- 83 testes Python passaram (78 anteriores + 5 novos), 6 avisos de depreciação.
- R$100 + quatro leituras + replay + processo Python novo = um registro de R$100.
- Dez chamadas concorrentes = uma inserção e nove replays.
- Payload conflitante: 409; novo UUID legítimo: segunda operação aceita.
- PIX removido permaneceu removido depois do replay.
- 5 testes frontend passaram: recarga do módulo com mesma storage, confirmação, separação por loja, resposta incompatível e storage indisponível.
- Primeira tentativa Jest falhou pela ausência de crypto no jsdom; mock corrigido e suite aprovada.
- Build frontend de produção compilou com avisos de dependências de hooks em componentes existentes.
- Build executado em cópia isolada, restaurando nela index.css remoto exato; não sobrescrever a divergência local do projeto.
- Nenhum lançamento real, envio de mensagem, migration, alteração de índice em produção ou deploy.

### Limites obrigatórios / não declarar etapa 1 concluída
- Persistência/restart testados com adapter SQLite durável que reproduz a restrição única; não havia mongod local. Ainda exige integração em Mongo descartável e teste UI completo no ambiente isolado.
- sessionStorage cobre reload da aba, não fechamento definitivo, outro dispositivo ou duas operações distintas abertas em abas diferentes.
- Clientes legados sem operation_id continuam aceitos e NÃO ficam idempotentes. Antes do deploy, definir rollout/corte do contrato e atualizar todos os chamadores.
- Novo frontend deve usar backend com este contrato; NÃO publicar somente o estático que ainda chama Emergent.
- Identificador ausente na resposta de servidor antigo exige conciliação pelo gestor; não criar UI de “limpar tentativa” que possa duplicar lançamento sem evidência.
- Quitação total, abatimento, crédito, pedidos e offline continuam pendentes.
- Ainda falta trilha uniforme de funcionário/antes/depois e fonte financeira única; não inventar funcionário em endpoint sem identidade autenticada.
- Recuperação de erros definitivos, retenção de operação após fechar aba e compatibilidade de browsers precisam de gate antes de produção.
- Rollback deste incremento é somente código da branch; não executar reversão de dados.

### Próxima ação concreta
Reproduzir e corrigir pay_all_prazo_customer com valor derivado da dívida remanescente, loja/cliente corretos e operação persistente atômica; avaliar transação Mongo antes de modificar múltiplos documentos.
Preservar o teste de replay e ampliar contra Mongo descartável antes de declarar idempotência geral.

## Incremento 1B.1 — não registrar recebimento sem quitação (22/09/2026)
### Causa confirmada e correção localizada
- As duas versões de pay_all_prazo_customer inseriam prazo_payments mesmo com update_many.modified_count=0. Isso gerava dinheiro fictício em chamadas repetidas ou sem dívida.
- Agora retornam HTTP 409 quando a gravação não quitou nenhum pedido, antes de criar recebimento ou histórico de pagamento.
- A mensagem orienta conferir o histórico; não retorna sucesso enganoso nem presume que uma chamada anterior concluiu todas as gravações.
- A condição usa o resultado efetivo da escrita, não find_one: a leitura pode estar desatualizada por outra quitação.
- Pagamento válido continua com mesmo contrato de sucesso. O frontend existente já exibe detail nas respostas de erro; não foi necessário alterá-lo.
- Corrigidos monólito (rota ativa) e router modular (rota duplicada). Não removidas rotas nesta alteração.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py (novo)
- GANOH_PROGRESS.md

### Verificação e testes aprovados
- Antes da alteração, os três arquivos existentes foram comparados integralmente com o commit 72d1495; iguais, sem trabalho paralelo nesses arquivos.
- Main confirmada em def13cf; branch ganoh/staged-audit confirmada em 72d1495.
- 91 testes Python aprovados (83 anteriores + 8 casos novos), 6 avisos de depreciação existentes.
- Nas duas implementações: quitação de R$100 e quatro repetições = somente um recebimento de R$100; repetições retornam 409.
- Cliente sem dívida: 409, nenhum recebimento ou histórico financeiro criado.
- Leitura inicial desatualizada seguida de zero pedidos alterados: 409, sem recebimento/histórico adicional.
- Senha inválida: 403 antes de qualquer acesso ao banco.
- Testes usam coleções em memória e mocks; não executam startup/jobs, banco real ou envio de mensagens.
- Não repetido build de frontend: nenhum arquivo frontend ou dependência mudou neste incremento; build anterior permanece registrado em 1A.

### Limites / bugs restantes
- NÃO é idempotência completa da quitação: update_many e insert_one ainda são operações separadas. Falha entre elas pode deixar dívida quitada sem recibo; deve ser reconciliada, não recriada automaticamente.
- Duas requisições podem dividir alterações de vários pedidos; o teste de leitura desatualizada NÃO comprova atomicidade multi-documento do Mongo.
- Retry após criação de nova dívida também exige ID persistente; o bloqueio desta etapa só cobre escrita que não alterou pedidos.
- Valor informado pelo cliente e filtro por nome sem loja permanecem problemas conhecidos. Não corrigir dados históricos ou afirmar valor real reconciliado.
- A proteção não deve ir a produção isoladamente; gates financeiros da etapa 1 continuam abertos.
- Nenhum deploy, migração, ajuste real de valores, índice em produção ou WhatsApp realizado.

### Próxima ação recomendada
1. Definir e validar em Mongo descartável transação/recuperação durável para quitação: pedidos + recibo + ID de operação precisam de resultado consistente.
2. Exigir loja no contrato de quitação e atualizar chamador; calcular centavos restantes no backend e impedir quitação de homônimos de outra loja.
3. Cobrir concorrência, falha entre escritas, restart, replay após nova dívida e conflito de payload antes de declarar incremento 1B completo.
4. Manter branch isolada e não avançar para tema/WhatsApp enquanto os gates financeiros estiverem pendentes.

## Incremento 1B.2 — loja e valor autoritativos na quitação (22/09/2026)
### Concluído
- Criado contrato específico para quitação total; a loja agora é obrigatória e limitada a runner ou gym-londres nas duas implementações.
- KitchenPage envia a loja atual junto com a confirmação. O contrato de pagamento individual não foi alterado.
- A busca usa nome escapado, sem correspondência parcial, e a loja informada. Cliente homônimo em outra unidade fica fora da quitação.
- A lista de IDs dos pedidos é congelada antes da escrita. Pedido novo criado depois da conferência não entra silenciosamente na quitação em andamento.
- O backend recalcula o saldo restante de cada pedido em centavos a partir de total e partial_paid; o recibo não usa mais o valor da tela como fonte financeira.
- Se o valor exibido ficou desatualizado, a API retorna 409 e exige atualizar a tela antes de confirmar.
- Valores são arredondados por pedido com Decimal e ROUND_HALF_UP. NaN, infinito e valor não positivo do pedido são bloqueados sem escrita.
- IDs ausentes/duplicados e mais de 1000 pedidos são bloqueados para não executar quitação parcial insegura.
- Se a quantidade alterada divergir da quantidade conferida, nenhum recibo/histórico é criado e a resposta orienta não repetir até conferência do gestor.
- Resposta de sucesso inclui amount e store efetivamente usados pelo backend.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- frontend/src/pages/KitchenPage.js
- GANOH_PROGRESS.md

### Testes e resultados
- 101 testes Python aprovados, 6 avisos de depreciação existentes.
- 18 casos diretos de quitação aprovados nas duas implementações: primeira quitação/replay, ausência de dívida, leitura desatualizada, senha, homônimos entre lojas, centavos, saldo da tela desatualizado e loja ausente/inválida.
- Caso de centavos: valores históricos fracionários são arredondados por pedido e o recibo usa o total calculado pelo servidor.
- Homônimo: quitação Runner de R$100 não alterou dívida Gym Londres de R$300.
- 5 testes Jest do mecanismo PIX continuaram aprovados.
- Build frontend de produção aprovado. Permanecem somente avisos de dependências de hooks já existentes; nenhum CSS foi alterado neste incremento.
- Testes não iniciaram jobs, não acessaram banco real e não enviaram WhatsApp.

### Limites / próxima ação
- Ainda não há atomicidade entre update_many dos pedidos e insert_one do recibo. O bloqueio de divergência evita um recibo inflado, mas uma falha pode deixar pedidos quitados sem recibo.
- Ainda não existe operation_id durável da quitação; retry após nova dívida não pode ser distinguido com segurança sem esse identificador.
- Os testes usam coleção em memória. Validar sessão/transação, concorrência, falha entre escritas e restart contra Mongo descartável antes de fechar 1B.
- Não executar reparo de históricos automaticamente. Divergências existentes exigem backup e reconciliação autenticada.
- Não publicar frontend separado: o backend Emergent atual não aceita o novo campo/contrato de forma coordenada.
- Próxima ação: 1B.3 deve criar registro de operação único e usar transação Mongo quando suportada, com comportamento seguro e documentado quando transações não estiverem disponíveis.
- Nenhum dado real, saldo, banco, serviço Render ou WhatsApp foi alterado; nenhum deploy realizado.

## Incremento 1B.3a — identificador durável da quitação (22/09/2026)
### Concluído
- operation_id UUID passou a ser obrigatório apenas na quitação total; pagamento individual permanece inalterado.
- A UI grava a operação em sessionStorage antes do POST e reutiliza a mesma chave após perda de resposta ou recarga da aba.
- Operações ficam em prazo_settlement_operations com _id determinístico por loja/operação; a unicidade nativa do Mongo funciona como trava de concorrência sem criar índice adicional.
- O registro pending é criado antes de alterar pedidos. Uma operação já concluída retorna a resposta original com replayed=true sem reler ou alterar dívidas.
- Mesma chave com cliente, valor ou forma de pagamento diferente retorna 409.
- Operação pending ou requires_review nunca é repetida automaticamente; exige conferência do gestor.
- Recibo passou a usar id e _id determinísticos derivados da operação e inclui operation_id.
- Falha com zero pedidos ou atualização parcial marca a operação como requires_review antes de responder 409.
- UI só descarta a chave em rejeições comprovadamente anteriores à escrita (senha/validação/saldo desatualizado). Erros ambíguos preservam e bloqueiam a tentativa.
- Resposta de servidor sem operation_id também bloqueia novas tentativas, evitando duplicidade durante implantação incompatível.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- frontend/src/pages/KitchenPage.js
- frontend/src/services/prazoSettlement.js (novo)
- frontend/src/services/prazoSettlement.test.js (novo)
- GANOH_PROGRESS.md

### Testes e resultados
- 107 testes Python aprovados, 6 avisos de depreciação existentes.
- 24 casos diretos de quitação aprovados nas duas implementações.
- Uma quitação de R$100 seguida de quatro replays retornou sucesso reaproveitado e manteve um único insert de recebimento.
- Replay com payload diferente: 409, sem segundo recebimento.
- Operação pendente: 409 e nenhum acesso/escrita em pedidos ou recebimentos.
- Restart real de processo Python com adapter SQLite durável: operação concluída foi reconhecida sem acessar pedidos/recebimentos e sem nova inserção.
- SQLite reproduz somente o contrato de unicidade/persistência do _id; não substitui teste de integração Mongo.
- 11 testes Jest aprovados (6 da quitação e 5 do PIX).
- Build frontend de produção aprovado; somente avisos de hooks preexistentes.
- Nenhum job iniciado, banco real acessado, mensagem enviada ou dado financeiro alterado.

### Limites / próxima ação
- A trava durável impede replay duplicado, mas pedidos, recebimento, histórico e status da operação ainda não estão em uma transação Mongo única.
- Queda após quitar pedidos e antes do recibo deixa pending e bloqueia retry; isso é deliberado para não inflar o caixa, porém requer ferramenta de reconciliação do gestor.
- Queda depois do recibo e antes de completed também bloqueia retry; não implementar recuperação automática sem conferir recibo e pedidos.
- No router modular, falha ao gravar o histórico após o recibo também deixa operação pendente; a rota ativa atual é o monólito, mas o caminho modular ainda precisa de transação.
- sessionStorage cobre recarga da aba, não outro dispositivo nem fechamento definitivo; o backend continua sendo a proteção durável.
- Ainda faltam teste concorrente e transação contra Mongo descartável/replica set. Não declarar a quitação totalmente atômica nem a etapa 1 concluída.
- Próxima ação: executar 1B.3b com Mongo descartável compatível com transações, incluindo falha injetada entre cada escrita e múltiplas chamadas concorrentes.
- Nenhum deploy realizado; manter a branch isolada até os gates financeiros e de ambiente serem concluídos.


## Incremento 1B.3a.1 — confirmação final não pode falhar silenciosamente (23/09/2026)
### Correção
- As duas implementações ignoravam o resultado ao mudar prazo_settlement_operations de pending para completed.
- Se a atualização retornasse modified_count=0, a API ainda respondia sucesso; um retry posterior encontraria pending e ficaria bloqueado, contradizendo a resposta anterior.
- Agora o resultado precisa confirmar exatamente uma alteração. Caso contrário, a API retorna 503 informando que o pagamento já foi registrado, orienta não repetir e pede conferência do gestor.
- O frontend já conserva o operation_id em respostas 503; nenhuma alteração de interface foi necessária.
- Nenhum recebimento ou pedido é repetido para tentar mascarar a falha.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- Teste novo injeta modified_count=0 na conclusão e exige HTTP 503 nas duas implementações, mantendo um único insert de recebimento.
- A lógica de decisão foi exercitada isoladamente: modified_count=1 retorna sucesso; 0 produz o bloqueio esperado.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado. Este ambiente renovado não possui dependências Python nem MongoDB; portanto o novo teste não foi executado com FastAPI nesta revisão.
- Não confundir esta verificação com transação Mongo. A lacuna pedidos + recibo + operação continua pendente para 1B.3b em replica set descartável.
- Nenhum dado real, deploy, Render, banco de produção ou WhatsApp foi alterado.

## Incremento 1B.3a.2 — validação e isolamento do pagamento parcial (23/09/2026)
### Correção
- O pagamento parcial agora rejeita zero, negativos, NaN, infinito e formas de pagamento desconhecidas nas duas implementações.
- A implementação modular agora exige a loja e filtra pedidos e saldo do cliente pela mesma unidade.
- Clientes homônimos da Runner e da Gym Londres não podem mais ter dívidas ou saldo misturados nesse caminho modular.
- A versão ativa já separava a consulta principal por loja; sua validação financeira foi endurecida sem mudar o fluxo válido.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e dos testes validada com ast.parse.
- Validação isolada dos modelos cobre zero, negativo, NaN, infinito, forma desconhecida e loja inválida.
- Regressões adicionadas para as duas implementações; a consulta modular é inspecionada para exigir a loja solicitada.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado. Este executor não possui todas as dependências do aplicativo; os novos testes FastAPI devem rodar no ambiente completo antes de merge/deploy.
- Esta correção não torna pagamentos parciais transacionais ou idempotentes. Essas lacunas continuam documentadas e nenhum deploy é autorizado.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.

## Incremento 1B.3a.3 — trava concorrente do saldo a favor (23/09/2026)
### Correção
- O pagamento parcial com saldo a favor lia o crédito e o substituía apenas pelo id do cliente.
- Duas requisições simultâneas podiam usar o mesmo saldo antigo e ambas seguir para alterar dívidas e registrar pagamento.
- A atualização agora compara id e saldo anterior. Somente uma requisição pode consumir aquele estado.
- Se o saldo mudar no intervalo, a API retorna 409 antes de alterar pedidos ou criar recebimento, orientando atualizar e conferir.
- A proteção foi aplicada nas implementações ativa e modular.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- Regressão adicionada para simular modified_count=0 no saldo; exige 409, pedidos intactos, nenhum recebimento e nenhum histórico.
- A decisão de concorrência também foi exercitada isoladamente para sucesso único e rejeição de estado desatualizado.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado. Este executor não possui FastAPI e as demais dependências, portanto a nova regressão deve rodar no ambiente completo antes de merge/deploy.
- A trava protege especificamente o saldo a favor. O pagamento parcial completo ainda precisa de operation_id, idempotência e transação Mongo para cobrir pedidos e recebimento.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.

## Incremento 1B.3a.4 — saldo a favor precisa existir e ser suficiente (23/09/2026)
### Correção
- Ao escolher payment_method=saldo, as duas implementações só validavam o crédito se o cliente existisse e o saldo fosse positivo.
- Cliente ausente ou com saldo zero pulava a dedução e ainda seguia para baixar a dívida e criar recebimento.
- Agora o saldo é obrigatório e precisa cobrir integralmente o valor antes de qualquer alteração financeira.
- Crédito inexistente, zerado ou insuficiente retorna 400 sem alterar pedido, recebimento ou histórico.
- A trava concorrente do incremento anterior permanece aplicada após essa validação.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- Regressões adicionadas para cliente sem cadastro e cliente com saldo zero nas duas implementações.
- A regra foi exercitada isoladamente para saldo ausente, insuficiente e suficiente.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado. Este executor não possui FastAPI e as demais dependências, portanto as novas regressões devem rodar no ambiente completo antes de merge/deploy.
- Pagamentos parciais ainda precisam de operation_id, idempotência e transação Mongo para pedidos e recebimento.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.

## Incremento 1B.3a.5 — pagamento individual não pode ser repetido (23/09/2026)
### Correção
- A rota que paga um único pedido atualizava também pedidos já pagos e retornava sucesso novamente.
- Agora a gravação exige prazo_paid diferente de true e confirma modified_count=1.
- Repetição ou pedido inexistente retorna 409 e não informa um novo sucesso.
- Valor zero, negativo, NaN, infinito e forma de pagamento desconhecida são rejeitados pelo modelo.
- A forma de pagamento usada passa a ficar registrada no pedido.
- A correção foi aplicada nas implementações ativa e modular.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- Regressão adicionada para primeira chamada com sucesso e repetição com 409 nas duas implementações.
- Entradas financeiras inválidas são testadas antes de qualquer acesso de escrita.
- A regra de atualização única foi exercitada isoladamente.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado. Este executor não possui FastAPI e as demais dependências, portanto as novas regressões devem rodar no ambiente completo antes de merge/deploy.
- Esta rota ainda não cria auditoria financeira completa; isso permanece pendente para a transação/auditoria centralizada.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.



## Incremento 1B.3a.6 — pagamento individual usa o saldo real do pedido (23/09/2026)
### Correção
- A rota individual ainda aceitava como definitivo o valor enviado pela tela.
- Agora o backend lê o pedido pendente e calcula o saldo real em centavos a partir de total menos partial_paid.
- Valor desatualizado enviado pelo frontend retorna 409 antes de qualquer gravação.
- A atualização compara atomicamente o total e o parcial previamente lidos; mudança concorrente também retorna 409.
- O pedido registra como pago somente o saldo calculado pelo banco, preservando loja e forma de pagamento.
- A correção foi aplicada nas implementações ativa e modular.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- Regressão adicionada para valor desatualizado da tela; exige 409 e nenhuma escrita.
- Regressão da repetição confirma valor e loja retornados, saldo parcial final e filtro otimista.
- A conversão monetária e as decisões de saldo foram exercitadas isoladamente em centavos.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado. Este executor não possui FastAPI e as demais dependências, portanto as novas regressões devem rodar no ambiente completo antes de merge/deploy.
- Esta rota ainda não cria auditoria financeira completa; isso permanece pendente para a transação/auditoria centralizada.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.


## Incremento 1B.3a.7 — pagamento parcial calculado em centavos (23/09/2026)
### Correção
- O abatimento parcial ainda subtraía e comparava valores monetários diretamente como float.
- Valores válidos como R$ 0,30 menos R$ 0,10 podiam resultar internamente em R$ 0,199999... e ser rejeitados como se R$ 0,20 excedesse a dívida.
- Total, parcela já paga, valor solicitado, saldo a favor e distribuição entre pedidos agora são calculados em centavos com Decimal e ROUND_HALF_UP.
- Registros e respostas recebem somente valores normalizados para duas casas decimais; valores abaixo de um centavo são bloqueados.
- A correção foi aplicada nas implementações ativa e modular.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- A falha anterior com 0,30 - 0,10 foi reproduzida isoladamente; o novo cálculo confirmou 20 centavos, quitação exata e saldo zero.
- Regressões FastAPI adicionadas para exigir que R$ 0,20 quite corretamente um pedido de R$ 0,30 com R$ 0,10 já pagos e para bloquear valores menores que R$ 0,01 nas duas implementações.
- O executor atual não possui FastAPI e pymongo; a regressão integrada deve rodar no ambiente completo antes de merge/deploy.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado.
- Pagamentos parciais ainda precisam de operation_id, idempotência persistente e transação Mongo para cobrir pedidos, saldo, recibo e histórico como uma única operação.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.


## Incremento 1B.3a.8 — idempotência persistente opcional no pagamento parcial (23/09/2026)
### Correção
- O abatimento parcial podia ser reenviado após perda de resposta e criar outro abatimento e outro recebimento.
- PrazoAbaterRequest agora aceita operation_id UUID opcional, preservando compatibilidade com clientes antigos.
- Quando informado, o identificador é persistido antes da primeira alteração financeira, usando o _id único do Mongo para bloquear concorrência.
- Repetição concluída retorna a resposta anterior com replayed=true, sem reler ou alterar pedidos e sem criar outro recebimento.
- Reutilização do mesmo identificador com cliente, loja, valor ou forma de pagamento diferentes retorna 409.
- Operação que ficou pendente não é repetida automaticamente e exige conferência do gestor.
- Falha ao marcar a operação como concluída não é informada como sucesso.
- A proteção foi aplicada nas implementações ativa e modular.

### Arquivos alterados
- backend/server.py
- backend/routers/prazo.py
- backend/tests/test_prazo_empty_settlement.py
- GANOH_PROGRESS.md

### Validação e limites
- Sintaxe dos dois módulos e do teste validada com ast.parse.
- A máquina de estados pending/completed, replay e conflito foi exercitada isoladamente.
- Regressões FastAPI adicionadas para repetição do mesmo UUID e conflito de payload nas duas implementações.
- A regressão anterior sem operation_id permanece, comprovando compatibilidade de entrada.
- O executor atual não possui FastAPI e pymongo; as regressões integradas devem rodar no ambiente completo antes de merge/deploy.
- A suíte completa anterior permanece em 107 testes Python, 11 Jest e build aprovado.
- Clientes antigos sem operation_id continuam sem proteção contra reenvio; a próxima integração de interface deve gerar e reutilizar o UUID até receber resposta definitiva.
- Ainda falta transação Mongo para agrupar pedido, saldo, recebimento, histórico e conclusão da operação.
- Nenhum dado real, banco de produção, WhatsApp ou Render foi alterado.
