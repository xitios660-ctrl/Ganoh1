# GANOH Android TV — relatório do incremento 0.1.0-demo

Solicitação: criar aplicativo separado para acompanhar o GANOH numa TCL Android TV, instalável pelo Downloader, mantendo Windows e site existentes. Base anterior: f192d08, branch feature/windows-offline-ganoh-2026 e PR #6 em rascunho.

## Arquivos

Somente novos arquivos em `tv/` e workflow `.github/workflows/ganoh-android-tv.yml`. Nenhum arquivo do Windows, frontend/backend web, Render, main ou produção foi alterado nesta etapa.

- `tv/android/`: projeto Android nativo sem WebView, Gradle Wrapper 8.9 com checksum, AGP 8.7.3, JDK 17, SDK/build-tools 35, mínimo Android 7/API 24, pacote com.ganoh.tv.demo.
- `MainActivity.java`: menu Android TV, foco de controle remoto, demonstração explícita, login de homologação, resumo/unidades/estoque, atualização, aviso de falha, logout e limpeza ao deixar o app.
- `CentralClient.java`: somente contratos existentes de consulta/login/logout do proprietário; TLS, sem redirect, timeout, limites de resposta. Nenhuma operação financeira ou credencial MongoDB.
- `Dashboard.java` e `StockPage.java`: centavos inteiros, consolidação por unidades autorizadas, rejeição de escopo/total incorretos, snapshot paginado sem mistura de gerações ou SKUs repetidos.
- Manifest/recursos: banner da TV, touchscreen não obrigatório, somente Internet, configuração TLS e exclusão de backup/transferência de dados.
- `src/test/`: 14 testes Robolectric/JUnit; `tv/tests/android_tv_smoke.py`: ensaio adb por controle remoto real em emulador/TV de testes.
- `tv/downloads/`: primeiro APK demonstrativo para link HTTPS direto; chave privada de assinatura fora do Git. CI só disponibiliza artefatos, sem publicar na Play Store ou modificar produção.

## Implementado

Painel de consulta para RUNNER/GYM LONDRES e consolidado de unidades autorizadas; vendas, despesas, caixa, prazo, diferenças, resultado, conflitos e revisão de caixa; estoque confirmado paginado; última operação central, falta de contato e pendências locais desconhecidas. Valores acumulados do livro, sem filtro diário. Não registra vendas na TV.

Demonstração funciona sem login/servidor e nunca acessa rede. Dados fictícios estão identificados permanentemente. O campo de servidor começa vazio: não abre o site existente nem Render. Login usa exclusivamente homologação HTTPS e sessão em memória. Falha preserva valores anteriores com aviso; sair/trocar de aplicativo limpa valores e senha/bearer locais. Sem cache financeiro em disco ou restauração de sessão.

## Testes já executados localmente

- `testDebugUnitTest`: 14 testes aprovados em Robolectric API 28/JDK 17: valores/unidades/escopo, duplicidade de SKUs, paginação, erro/expiração, redirects, limite de resposta, foco/ações, recriação e limpeza ao sair.
- `lintRelease` e `assembleRelease`: aprovados, 0 erros e 1 aviso esperado sobre atributo dataExtractionRules (só usado em Android 12+; versões anteriores usam allowBackup/fullBackupContent desabilitados).
- SDK/JDK instalados somente no ambiente de build, fora do repositório. Certificados/proxy do ambiente foram configurados só para downloads de dependências; TLS do aplicativo permanece padrão, sem bypass.
- Não há KVM disponível neste ambiente. Teste de instalação/controle real no emulador foi preparado para CI; execução/resultados serão acrescentados após validação. Nunca declarar teste físico na TCL sem fazê-lo.

## Limitações e próximas etapas

Não é painel de produção nem contém números reais do site. Depende de servidor HTTPS isolado e conta de homologação previamente provisionados para consulta autenticada; nenhuma hospedagem foi criada. O backend atual emite sessão de proprietário, não um token exclusivo de leitura/pareamento para TV. A interface só consulta, mas a autorização central específica de TV ainda precisa ser implementada antes de uso comercial.

Faltam homologação física na TCL, testes de versões Android anteriores/posteriores, filtro diário/histórico, assinatura comercial estável e mecanismo seguro de atualização. APK inicial tem chave de demonstração local; builds CI usam outras chaves descartáveis e não são upgrades diretos garantidos. Nenhuma chave, senha real ou token entra no APK/repositório. O Windows permanece na versão anterior validada; este incremento não modifica seu comportamento ou o sistema das lojas.
