# GANOH Desktop (Windows): protótipo de núcleo offline

**NÃO usar em produção. Não é instalador, não é backend local completo e NÃO realiza pagamentos.**

Este diretório contém um diário SQLite transacional e um coordenador de sincronização *sem transporte real* para validar as principais garantias antes de integrar o Windows ao GANOH React/FastAPI.

## Execução dos testes

No repositório, com Python 3.11+ e sem dependências extras:

```powershell
python -m unittest discover -s desktop/tests -p "test_*.py" -v
```

Também existe o fluxo de GitHub Actions em `.github/workflows/ganoh-offline-tests.yml` rodando em `windows-latest` e `ubuntu-latest`.

## API de protótipo para desenvolvedores

```python
from desktop.offline_store import OfflineJournal
from desktop.sync_worker import sync_once

# Em produção futura, usar %LOCALAPPDATA%/GANOH/Runner/ e protegê-lo.
journal = OfflineJournal("exemplo-runner.sqlite3", "runner")
sale = journal.record_sale(
    sale_id="pedido-local-123", total_cents=1990, payment_method="cash",
    items=[{"sku": "lanche-01", "quantity": 1}],
)
print(journal.status())  # pending=1; arquivo persiste após fechar o programa

# deliver deve ser um CLIENTE AUTENTICADO de uma API central idempotente.
# NÃO usar o /api/orders/sync legado; ele pode repetir os efeitos da venda.
# sync_once(journal, deliver)
```

As vendas desta fase são apenas rascunhos de eventos locais, não comprovantes bancários, baixa de estoque nem pagamento efetivo. `sync_once` exige recibo compatível com operação, unidade e hash; após erro de rede, repete a mesma UUID. O servidor central precisará implementar a deduplicação efetiva em transações MongoDB.

## Preparação para o instalador

1. Criar API FastAPI local dedicada, compatível com os endpoints que o React usa, e migrar operações gradualmente para repositórios SQLite por unidade.
2. Integrar o React existente ao serviço local via loopback com autenticação, preservando rotas e visual.
3. Criar `desktop/electron/` com `contextIsolation`, `nodeIntegration=false`, `sandbox`, CSP e inicialização de serviço local empacotado.
4. Empacotar Python para Windows com PyInstaller; construir .exe com electron-builder no GitHub Actions Windows; assinar digitalmente e publicar apenas após homologação.
5. Gerenciar atualização com verificação de assinatura, migrações SQLite versionadas e rollback; nunca substituir dados ou descartar fila pendente.
6. Testar em dois PCs reais Windows com conexões interrompidas, fila de dezenas de eventos, desligamento forçado, conflito de estoque e contas a prazo.

Documentação detalhada: `docs/WINDOWS_OFFLINE_MIGRATION.md`.

## Segurança e limitações

- Arquivo SQLite de demonstração **sem criptografia**: somente dados fictícios.
- Sem conexão ao Atlas, sem credenciais de banco, sem endpoint de sincronização real.
- Sem instalador Windows pronto ou paridade funcional com a interface atual.
- Fluxos de cobrança PIX, cartão, prazo, estorno e ajustes de estoque **não** estão implementados offline.
- Nenhuma atualização desta branch foi enviada a `main`, Render ou MongoDB.
