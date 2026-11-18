# GANOH Windows — demonstração 0.4.0

Somente dados fictícios e ambiente isolado. Não substitui o site das lojas nem está homologado para atendimento real. O build normal do site continua com as telas originais.

## Uso local

1. Instalar o artefato DEMO UNSIGNED do workflow da branch de desenvolvimento.
2. Escolher RUNNER ou GYM LONDRES na primeira abertura. Vínculo permanente por dispositivo/unidade; dados em `%LOCALAPPDATA%/GANOH-Demo/<unidade>/`.
3. Criar o primeiro proprietário local com senha forte (mínimo 12 caracteres). Não existe senha padrão. Criar perfis de caixa ou cozinha conforme necessidade.
4. Abrir o caixa com contagem igual ao saldo do livro. Proprietário pode cadastrar produtos e lançar entrada de estoque; catálogo também pode vir de snapshot de homologação.
5. Registrar venda em dinheiro, despesa ou cliente offline. Fechar/reabrir conserva operações e saldo. Cozinha pode atualizar preparação/entrega sem visualizar finanças.
6. Para prazo: cadastrar cliente, autorizar limite como proprietário e sincronizar essa aprovação com a central antes de usar o crédito. Recebimento em dinheiro exige recibo único; não conta receita novamente.
7. Fechar caixa com contagem. Diferença bloqueia nova abertura e exige reconciliação explícita do proprietário com motivo, mantendo contagem original e lançamento de diferença.

A interface é operacional dedicada com tema/componentes existentes, sem paridade integral de todas as telas do site. PIX/cartão não são liquidados offline. Cancelamentos/estornos e download de clientes/saldos centrais ainda faltam.

## Persistência e segurança

Electron isolado/sandbox/contextIsolation, sem Node no renderer, backend PyInstaller oculto em loopback com porta efêmera, token no processo principal e credencial por stdin. API valida bearer, origem/host e sessão de operador. Sessões HttpOnly SameSite strict expiram e são revogadas ao desativar/resetar conta. Auditoria local associa operador aos eventos. Nenhuma credencial Atlas é distribuída.

SQLite usa SQLCipher inclusive WAL; chave e token do dispositivo usam DPAPI do usuário Windows. Não há fallback plaintext nem substituição de banco ao perder chave. Instalador não escreve no diretório dos dados. Schema 3 faz evolução aditiva e recusa versões futuras; restauração/rollback reais precisam de homologação.

Proprietário pode exportar backup cifrado consistente, protegido por frase de recuperação com pelo menos 16 caracteres. Guardar frase separadamente. A opção verificar restaura em diretório novo e revoga sessões copiadas, sem trocar o banco ativo. Não basta copiar o arquivo SQLite sem a chave. Recuperação ativa e backups automáticos ainda pendentes. CSV do livro é provisório, em centavos, com escape de fórmulas.

## Sincronização de homologação

Suporte configura `sync.json` com `{"origin":"https://servidor-de-homologacao"}` e provisiona `device-token.dpapi` pela mesma conta Windows. Central desta branch aceita somente `ganoh_sync_test_*`, nunca produção. Cada dispositivo precisa de permissões explícitas por operação/unidade. Não configurar endpoint legado.

Worker automático e botão manual não seguram o bloqueio de gravações durante chamadas de rede. Fila persistente global preserva causalidade e para em confirmação desconhecida. UUID e fingerprint imutáveis, índices únicos e transação central unem inbox, estoque e livro; reenvio após resposta perdida devolve o recibo sem duplicar efeito.

Snapshots imutáveis por geração, páginas de 100, cursor por dispositivo/unidade, expiração 24h e limite de 1.000 SKUs. Staging só publica ao finalizar; interrupção retoma cursor. Cobertura com UUID+hash distingue reservas já aplicadas para não descontar estoque duas vezes. Até 100 UUIDs pendentes por solicitação. Versão/regressão inválida não substitui catálogo publicado. Estoque insuficiente ou versão divergente gera conflito visível.

Revisão central exige proprietário, unidade autorizada, UUID, versão e motivo; decisões retain/reject são auditadas e não apagam venda nem ajustam dinheiro silenciosamente. UI de revisão e download de resoluções ainda faltam. Caixa/recebíveis locais são provisórios enquanto pendentes ou conflitantes.

## Painel separado do proprietário

Build `REACT_APP_OWNER_PANEL=true REACT_APP_SYNC_ORIGIN=https://central-de-homologacao`. Sem origem HTTPS não faz conexão; não existe fallback para produção. Provisionamento de conta usa `backend.sync_v1.owner_auth.provision` exclusivamente no banco descartável e lista explícita de unidades. CORS exige origem HTTPS autorizada em `create_app(..., owner_origins=...)`. Não há cadastro público de proprietário.

Login, sessão em memória, logout/revogação e unidades autorizadas; mostra somente lançamentos centrais confirmados, estoque paginado, última comunicação/sincronização e aviso de atraso. Pendências ainda nos PCs são desconhecidas. Não existe implantação HTTPS pronta; o painel financeiro atual segue intacto. GitHub Pages pode servir interface, mas exige backend autenticado em outra hospedagem.

## Validação

- `python -m unittest discover -s desktop/tests -v`
- MongoDB replica set descartável em loopback 27028: `python -m unittest discover -s backend/sync_v1/tests -v`
- `CI=true npm --prefix frontend test -- --watch=false --runInBand --testPathPattern="Desktop|desktopMoney|OwnerOverview"`
- Build desktop: `REACT_APP_DESKTOP_DEMO=true GENERATE_SOURCEMAP=false npm --prefix frontend run build`
- Painel mobile Chromium: `python -m backend.sync_v1.tests.browser_owner_smoke` após compilar em `frontend/build-owner` com origem `https://central.example` (interceptada somente pelo teste).
- Chromium real: `python -m desktop.tests.browser_demo_smoke` (transporte central TestClient, não HTTPS externo).
- Windows: `python desktop/tests/windows_packaged_smoke.py`; CI também executa sobre PyInstaller e NSIS, com restart forçado, reinstalação, backup/recuperação e preservação de chave/dados.

CI não equivale a homologação interativa Electron em Windows 10/11 ou dois computadores. Upgrade entre versões distintas, assinatura, servidor HTTPS, provisionamento real, restauração ativa e paridade financeira completa continuam obrigatórios antes do uso real. Histórico de resultados/artefatos em [relatório técnico](../docs/CODEX_WINDOWS_PROGRESS_2026-11-18.md).
