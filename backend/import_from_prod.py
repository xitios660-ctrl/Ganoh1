"""Retired unsafe importer. Never loads credentials or connects on import/run.

Use backend.data_bridge.mongo_backup for read-only capture and isolated restore
verification, followed by a scoped unit package. This legacy script previously
wiped collections and cannot be used to migrate real GANOH data safely.
"""


def main():
    raise SystemExit('Importador destrutivo retirado. Nenhum dado foi alterado. Use a captura somente leitura e a restauração isolada de backend.data_bridge.')


if __name__ == '__main__':
    main()
