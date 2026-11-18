# GANOH Windows — demonstração operacional 0.4.0

React local, FastAPI oculto, SQLCipher e Electron/NSIS. Instalação por atalho sem terminal; dados por unidade fora da pasta do aplicativo. Somente homologação com dados fictícios: não substitui o site ou constitui paridade completa.

Implementados: venda em dinheiro/prazo aprovado, fila persistente/idempotente, reserva de estoque, snapshots retomáveis, caixa por turno e reconciliação, despesas, clientes, recebimentos, cozinha, contas por perfil, backup cifrado recuperável em diretório isolado e CSV provisório. Central e novo painel do proprietário são exclusivos de banco descartável `ganoh_sync_test_*`; nenhuma credencial Atlas no Windows.

- [Uso, segurança e configuração](DEMONSTRATION.md)
- [Matriz de paridade e pendências](../docs/DESKTOP_PARITY.md)
- [Evidências, commits, CI e artefatos](../docs/CODEX_WINDOWS_PROGRESS_2026-11-18.md)
- [API central isolada](../backend/sync_v1/README.md)

## Testes

Python 3.11; instalar `desktop/requirements.txt`. Da raiz:

```sh
python -m unittest discover -s desktop/tests -p "test_*.py" -v
```

Windows executa DPAPI e ensaios do launcher/PyInstaller/NSIS pela CI; Linux pula apenas os testes específicos de DPAPI. Testes diretos do diário usam fixtures sem chave somente onde necessário; o launcher exige SQLCipher e DPAPI sem fallback plaintext.

Não conectar a API legada `/api/orders/sync`. Não modificar UUID/hash para contornar conflito. Não abrir dados reais, migrar produção ou instalar como substituto das lojas. Ainda faltam estornos/cancelamentos, todas as telas originais, snapshots de clientes/saldos, assinatura, HTTPS homologado, recuperação ativa e homologação interativa nos dois PCs. O site atual permanece em operação.
