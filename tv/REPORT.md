> Estado atual: incremento **0.2** ao final deste relatório. As seções 0.1 abaixo preservam a evidência histórica; a limitação de usar credencial de proprietário foi resolvida na central isolada.

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
- Não há KVM disponível neste ambiente. Por isso, a instalação e o controle real no emulador foram validados na CI, conforme a seção de resultado final. Nunca declarar teste físico na TCL sem fazê-lo.

## Limitações e próximas etapas

Não é painel de produção nem contém números reais do site. Depende de servidor HTTPS isolado e conta de homologação previamente provisionados para consulta autenticada; nenhuma hospedagem foi criada. O backend atual emite sessão de proprietário, não um token exclusivo de leitura/pareamento para TV. A interface só consulta, mas a autorização central específica de TV ainda precisa ser implementada antes de uso comercial.

Faltam homologação física na TCL, testes de versões Android anteriores/posteriores, filtro diário/histórico, assinatura comercial estável e mecanismo seguro de atualização. APK inicial tem chave de demonstração local; builds CI usam outras chaves descartáveis e não são upgrades diretos garantidos. Nenhuma chave, senha real ou token entra no APK/repositório. O Windows permanece na versão anterior validada; este incremento não modifica seu comportamento ou o sistema das lojas.

## APK gerado e verificado

- Código: [acfab8b](https://github.com/xitios660-ctrl/Ganoh1/commit/acfab8b), normalização do wrapper [0216aca](https://github.com/xitios660-ctrl/Ganoh1/commit/0216aca).
- APK release universal (sem bibliotecas nativas), 37.677 bytes; assinatura v2/v3 RSA-2048 validada por apksigner. Manifest conferido com aapt: API mínima 24, target 35, launcher leanback, touchscreen opcional e somente permissão INTERNET; sem debuggable.
- SHA-256 do APK conferido localmente: `48a7be1a91928c8a042df4d277751e26ef069c32802f78e8b1ff2d3803a79bbb`. SHA-256 do certificado de demonstração: `239e868973f764daa9742dce6aebf72a8ed06943d2cfd5f96f9998a162cf9243`.
- O APK está versionado em tv/downloads para permitir URL direta no Downloader sem depender de ZIP/autenticação de artefato. Repositório confirmado público; o APK não inclui conta, token, senha ou hostname de produção. Não foi criado release comercial nem modificado serviço hospedado.
- CI verificou tanto o APK recompilado como este APK direto em emulador, além do checksum e testes, conforme os resultados abaixo. Teste físico TCL não realizado.

## Resultado final da automação — 20/11/2026

- [CI Android TV aprovada](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44662892315), código 1e4de71: wrapper validado, checksum do APK direto conferido, testes/lint/build e assinaturas aprovados.
- Emulador **Android TV API 29/x86, perfil TV 1080p** executou tv/tests/android_tv_smoke.py duas vezes, uma com o APK recompilado da CI e outra com o **APK exato do link direto**: instalar, abrir a Activity registrada para o menu TV, usar DPAD/OK, abrir estoque RUNNER, voltar, sair, encerrar forçado e reinstalar; reabertura sem restaurar valores/sessão. Ambos aprovados. FLAG_SECURE preservado, validação via XML de acessibilidade; sem alegação de teste físico ou screenshot da TCL.
- [Artefatos da CI](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44662892315/artifacts/14596273582) são ZIP temporário com APK assinado por outra chave de teste. Para Downloader, usar o APK direto estável de tv/downloads, que também foi testado no emulador. [Relatórios JUnit/lint](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44662892315/artifacts/14596766030), retenção até 04/12/2026.
- [Regressão Windows/Linux/central/React aprovada](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44662899184). Código Windows/web/central não foi alterado nesta etapa.
- Link público direto baixado por HTTPS com status 200 e SHA-256 igual ao APK gerado, sem depender de login, ZIP ou Render. [Baixar APK](https://raw.githubusercontent.com/xitios660-ctrl/Ganoh1/feature/windows-offline-ganoh-2026/tv/downloads/GANOH-TV-demo.apk).
- Primeira CI falhou ao tentar instalar o pacote legado Android tools, removido do repositório SDK. Workflow corrigido para platform-tools explícito; repetição aprovada. Erro não foi ocultado.
- Commits: [acfab8b — código/testes](https://github.com/xitios660-ctrl/Ganoh1/commit/acfab8b), [0216aca — wrapper](https://github.com/xitios660-ctrl/Ganoh1/commit/0216aca), [44eb557 — APK/link](https://github.com/xitios660-ctrl/Ganoh1/commit/44eb557), [1e4de71 — CI](https://github.com/xitios660-ctrl/Ganoh1/commit/1e4de71). PR #6 permanece em rascunho.

**Entregue:** APK instalável demonstrativo, testado em Android TV virtual, com cliente de consulta de homologação e link para Downloader. **Não entregue como concluído:** números reais de produção, servidor HTTPS novo, credencial TV dedicada, Play Store, teste físico TCL e atualização comercial assinada. Próxima etapa: testar instalação/legibilidade/controle na TCL e preparar acesso central dedicado à TV em ambiente isolado, antes de qualquer integração real. Nenhum dado real foi acessado ou alterado.

## Incremento 0.2 — credencial dedicada e revogável de consulta

Implementado: backend/sync_v1/tv_auth.py com contas/sessões exclusivas, escopo tv:read, scrypt, bloqueio por falhas, validade de 8h, revogação e auditoria snapshot/majority. Autorizações de proprietário e dispositivo não aceitam esses tokens. Cada consulta usa a interseção das unidades da conta com as unidades atualmente autorizadas ao proprietário; revogação do proprietário também bloqueia a TV. Cadastro é protegido, sem endpoint público; senha não pode repetir a do proprietário. Respostas autenticadas não são armazenáveis em caches.

service.py ganhou rotas /tv/* e /owner/tv-accounts; cálculo de resumo/estoque foi extraído para helpers compartilhados, preservando contrato do proprietário. Nenhum servidor legado de produção foi importado/montado. Índices e coleções são adicionados exclusivamente no banco isolado permitido, sem migração destrutiva.

Novo DesktopTVAccessPanel.jsx é montado somente no build separado do proprietário: criar usuário/senha/unidades e revogar pelo navegador, inclusive celular. Campos de senha são apagados, sem localStorage. Cadastros são relidos após a tentativa, inclusive resposta perdida; usuário único evita contas duplicadas.

Android 0.2 exige resposta tv:read em /tv/login e não usa mais /owner/login. Nome/pacote mantidos; versionCode 2 e mesma chave do APK direto 0.1. APK atual SHA-256: `228ed3f0ae876f68292ed8d77d3684730a543bca77c1f98d9d9e26fa76399cc7`. Assinatura e manifest verificados, sem debuggable e somente INTERNET. A versão 0.1 foi guardada como fixture de upgrade; não é o download indicado para uso.

Arquivos: backend/sync_v1/{service,tv_auth}.py; testes test_tv_access.py/browser_owner_smoke.py; React DesktopTVAccessPanel e integração/testes OwnerOverview; Java CentralClient/MainActivity e testes; app/build.gradle; teste adb de atualização; workflow Android TV; APK/SHA256SUMS e documentos. Commits iniciais: b8a9874 (central), a149ff9 (cliente/painel/upgrade).

Testes locais executados: 32 testes MongoDB aprovados (25 anteriores + 7 de TV), 15 Android aprovados, 13 React aprovados, 2 Node aprovados, 56 desktop executados (54 aprovados + 2 DPAPI específicos do Windows pulados em Linux). Lint Android sem erros, 1 aviso conhecido de atributo usado só no Android 12+. Build separado do proprietário aprovado. Chromium mobile real aprovou criar conta RUNNER, obter consulta TV, negar revisão financeira e revogar; sessão perdeu acesso na consulta seguinte. Backend central é TestClient com MongoDB local, não servidor HTTPS publicado.

O primeiro fixture MongoDB local não iniciou por falta de espaço no ambiente restaurado. Apenas esse container descartável foi removido e recriado com /data/db em tmpfs; testes foram repetidos com sucesso, sem apagar dados reais ou volumes desconhecidos.

CI de upgrade 0.1→0.2 e APK novo ainda será registrada após execução. Não declarar teste físico na TCL ou acesso real aos números das lojas. Continuam pendentes hospedagem HTTPS de homologação, validação física e assinatura/atualização comercial. O novo login precisa da versão nova da central isolada; servidor antigo falha sem fallback para conta de proprietário ou produção.

### Validação final da versão 0.2

- [CI Android TV aprovada](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44731153718) no commit c67f5f3: 15 testes Android, lint/build, checksum e assinatura. Execução duplicada também [aprovada](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44731161136).
- Emulador Android TV API29/1080p aprovou tanto o APK recompilado quanto o arquivo exato do link direto. A segunda rodada instalou a fixture real 0.1, abriu demonstração, encerrou o processo e **atualizou para 0.2 sem desinstalar**. Depois validou DPAD/estoque/voltar/saída/reabertura/reinstalação, sem restaurar valores/sessão. Não foi ensaiada preservação de origem preenchida nem teste físico TCL.
- [Regressão completa aprovada](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44731153754): 56 testes desktop no Windows, Linux 54+2 skips DPAPI, 32 centrais, 13 React e 2 Node; builds desktop/gestor. [Instalador Windows aprovado](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44731153678), sem mudanças no núcleo Windows ou uso de dados reais.
- [Relatórios Android](https://github.com/xitios660-ctrl/Ganoh1/actions/runs/44731153718/artifacts/14625399749), retenção de 14 dias. O APK direto não expira com o artefato de CI; download público HTTPS retornou 200 e SHA-256 igual ao registro da versão 0.2.
- Commits: [b8a9874 — autorização](https://github.com/xitios660-ctrl/Ganoh1/commit/b8a9874), [a149ff9 — aplicativo/painel/upgrade](https://github.com/xitios660-ctrl/Ganoh1/commit/a149ff9), [594943c — confirmação majority/entrada mobile](https://github.com/xitios660-ctrl/Ganoh1/commit/594943c), [c67f5f3 — APK/documentos](https://github.com/xitios660-ctrl/Ganoh1/commit/c67f5f3). PR #6 segue rascunho, sem merge/deploy.

Próxima etapa: disponibilizar central e painel de **homologação HTTPS** em infraestrutura aprovada e validar a TCL real. A credencial de consulta já está implementada; pareamento por código/QR não foi implementado, pois o fluxo atual usa usuário/senha exclusivos. Não apresentar esta entrega como integração de produção ou aplicativo comercial completo. Fonte/backend web de produção, main, Render e ganoh_production permaneceram intactos.
