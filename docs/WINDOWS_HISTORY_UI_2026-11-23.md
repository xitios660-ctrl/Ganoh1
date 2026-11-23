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
