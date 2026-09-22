# GANOH — Continuidade do trabalho

## Etapa atual
Etapa 1 em andamento — incremento 1A (PIX manual) implementado e validado localmente.
Etapa 0 — auditoria de código e navegação pública concluída em 22/09/2026.
Validação autenticada, reconciliação do banco real e confirmação dos segredos de implantação continuam pendentes; não declarar produção validada.
Próximo incremento: 1B, corrigir a quitação total que gera recebimento mesmo sem dívida. Não avançar à etapa 2 enquanto os gates financeiros estiverem pendentes.

## Retomada obrigatória
1. Ler este arquivo e os commits da branch ganoh/staged-audit e da main.
2. Conferir diff e estado do código antes de editar. Não refazer correções existentes.
3. Testar sem startup conectado a banco real, sem envio de WhatsApp e sem lançamentos reais.
4. Atualizar este registro e criar commit após cada incremento validado.
5. NÃO enviar a main ou fazer merge/deploy antes das etapas 1–11 e do checklist da etapa 12.
6. Se automações antigas continuarem, devem respeitar esta branch e este plano; não publicar correções isoladas na main.

## Base, rollback e último commit
- Base de código auditada: def13cf952811907329e0da79544699b2783ee37.
- Último commit anterior a esta atualização: 5b6c7a5940f06bade684b9280a99b2c4a299d510 (auditoria concluída).
- O commit que contém este diagnóstico é obtido por git log -1 -- GANOH_PROGRESS.md. Um arquivo não pode conter o próprio SHA final.
- Rollback de código: conservar a base e reverter somente commits novos, sem apagar dados ou forçar referências.
- Rollback de banco ainda NÃO existe como backup verificado. Não executar migração ou reparação de dados.
- Main e branch de trabalho foram conferidas na retomada; main continuava na base.
- Não foi encontrado AGENTS.md na árvore remota auditada nem no workspace.
- Checkout local é parcial, majoritariamente não rastreado: não usar git add . nem enviar o diretório inteiro.
- Comparação de blobs locais com árvore remota: diferenças de newline em vários arquivos; diferença substantiva em frontend/src/index.css. CSS remoto foi consultado separadamente. Reobter fontes exatas antes do build final.

## Arquivos alterados nesta etapa
Somente GANOH_PROGRESS.md. Nenhum código de aplicação, configuração de produção, dado ou saldo alterado.
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
Retomar a etapa 1 pelo incremento 1B de quitação total em ganoh/staged-audit; ler primeiro o registro 1A abaixo.
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
