# GANOH TV — Android TV / Google TV (TCL)

Aplicativo **separado** do Windows e do site. Painel nativo Java/Android para controle remoto, sem WebView, MongoDB, vendas ou movimentações financeiras locais. Pacote `com.ganoh.tv.demo`, versão `0.2.0-demo`, Android 7/API 24 ou superior. Não é Roku, Tizen ou webOS; não foi publicado na Play Store.

## Instalação pelo Downloader

O primeiro APK de demonstração validado está em `tv/downloads/GANOH-TV-demo.apk`. Link direto:

https://raw.githubusercontent.com/xitios660-ctrl/Ganoh1/feature/windows-offline-ganoh-2026/tv/downloads/GANOH-TV-demo.apk

1. No Downloader da Android TV, abrir o link e baixar o APK.
2. Se a TV solicitar, permitir instalação de aplicativos desconhecidos **para o Downloader** e confirmar a instalação do GANOH TV Demo.
3. Abrir o GANOH TV Demo no menu da TV e escolher **Abrir demonstração — dados fictícios**. Não precisa de computador, usuário ou servidor para essa demonstração.
4. Usar setas e OK do controle. Voltar sai do estoque para o resumo; **Sair da demonstração** retorna à tela inicial.

O APK 0.2 é assinado com a mesma chave do APK direto 0.1, para permitir atualização sem desinstalar. A CI testa esse upgrade. É uma chave de desenvolvimento dedicada à demonstração, não uma identidade comercial homologada. A chave fica fora do Git. Builds automáticos de CI usam chave descartável própria; portanto, APKs de builds diferentes podem não atualizar uns aos outros. Antes de distribuição comercial, definir assinatura estável e estratégia de atualização. Esta versão não guarda vendas, senha ou sessão na TV.

Não instalar um arquivo de origem diferente fingindo ser o mesmo aplicativo. SHA-256 e evidências de teste ficam em [REPORT.md](REPORT.md). Nenhum código numérico de terceiros para o Downloader foi criado.

## O que aparece

- RUNNER e GYM LONDRES separadas; consolidado somente das unidades autorizadas.
- Vendas, despesas, caixa, valores a prazo, diferenças de caixa e resultado do livro.
- Estoque confirmado por unidade, em snapshot paginado e versionado.
- Última operação confirmada, conflitos/caixas em revisão, aviso de falta de contato da loja e de falha ao consultar a central.
- Valores acumulados do livro, **sem filtro diário**. Operações ainda nos PCs offline são desconhecidas, nunca tratadas como faturamento consolidado.

A demonstração tem aviso permanente de dados fictícios e não acessa nenhuma rede. Seus números não são os do site atual. A interface foi adaptada para leitura na TV e controle remoto, preservando identidade GANOH; não substitui todas as telas do gestor original.

## Consulta autenticada de homologação

Campo de servidor vazio por padrão. Responsável técnico configura origem HTTPS da central v1 isolada; usar somente uma conta exclusiva de TV criada pelo proprietário na homologação. Sem fallback para Render, site ou API legada. O servidor da branch aceita apenas bancos `ganoh_sync_test_*`; nenhuma hospedagem nova foi implantada.

A TV 0.2 usa somente `tv/login`, `tv/overview`, `tv/stock` e `tv/logout`. No painel separado do proprietário, a seção **Acessos exclusivos para Android TV** cria um usuário/senha diferente da conta do proprietário e permite escolher as unidades e revogar o acesso. Só mostra unidades autorizadas e aceita o escopo `CONFIRMED_ISOLATED_V1_LEDGER`. O aplicativo não contém endpoints de alterações financeiras ou conexão com banco. Apenas a central isolada ganhou essas rotas; o backend web de produção permanece intacto.

**Autorização exclusiva de consulta:** as contas e sessões de TV ficam em coleções separadas das contas de proprietário/dispositivos. A senha da TV precisa diferir da senha atual do proprietário. O token `tv:read` não autoriza vendas, revisão de conflitos ou criação/revogação de acessos. O servidor revalida a conta, o proprietário e a interseção de unidades em cada consulta. Revogar a conta encerra as sessões; desativar o proprietário também impede novas consultas.

As credenciais são criadas por proprietário autenticado; não há cadastro público. Senhas usam scrypt e sessões aleatórias ficam no servidor somente por hash, com validade de 8h e bloqueio após tentativas inválidas. Criação/revogação são auditadas em transações snapshot/majority. Respostas autenticadas usam Cache-Control: no-store.

O resumo é consultado a cada 30 segundos enquanto aberto; estoque é snapshot identificado por geração/data e pode ser atualizado explicitamente. Falhas preservam o último resumo **em memória**, com aviso de desatualização. Sem resumo anterior, não inventa saldo zero. Não há cache financeiro em disco. Voltar para outro aplicativo encerra a sessão local e tenta logout; sem rede, a sessão central expira conforme política existente (8h).

## Segurança e construção

- Apenas HTTPS/porta 443, certificados do sistema, sem redirects, URL com credenciais, query ou caminhos arbitrários.
- Timeout, limite de resposta de 1 MiB e validação de centavos inteiros, unidade, totais, paginação e geração de estoque.
- Internet é a única permissão; sem câmera/microfone/arquivos, analytics ou fontes externas.
- Senha/bearer só em memória; não entram em SharedPreferences, bundle de restauração, logs ou APK. Somente a origem não secreta pode ser guardada.
- Backup Android desabilitado, tela protegida por FLAG_SECURE e limpeza ao sair/trocar de aplicativo. Dispositivo comprometido/root e segurança física não foram homologados.
- A TV não precisa do FastAPI/SQLite local: consulta o servidor central por HTTPS. Windows continua com seu funcionamento offline independente.

JDK 17, SDK Android 35 e build-tools 35.0.0:

```sh
cd tv/android
./gradlew testDebugUnitTest lintRelease assembleRelease
```

Gradle Wrapper 8.9 com SHA-256 da distribuição. APK release precisa de assinatura externa antes de instalar. Nenhuma chave privada está no repositório. A CI gera APK demonstrativo assinado, testa em emulador Android TV e publica artefato temporário; não faz deploy em lojas/Render/produção e não publica na Play Store.

`tv/tests/android_tv_smoke.py APK` instala/reinstala via adb em emulador/TV de teste, usa DPAD real, confere demonstração, estoque, voltar, logout e reabertura sem dados financeiros. Nunca usar esse ensaio contra instalações reais existentes. FLAG_SECURE não é desabilitado para capturar imagem.

Faltam teste físico na TCL do proprietário e servidor HTTPS de homologação. A conta de consulta dedicada já foi implementada e testada em ambiente isolado. Consulte o relatório para distinguir testes executados dos apenas preparados.
