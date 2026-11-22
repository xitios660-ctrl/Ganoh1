# Backup e carga inicial: infraestrutura em validação

Estas bibliotecas não executam importação automaticamente, não carregam `.env` e não
importam o servidor de produção. Não existe autorização implícita para escrever na
origem. O cliente MongoDB é fornecido pelo operador no ambiente central seguro;
credenciais administrativas nunca devem integrar o instalador Windows.

Fluxo obrigatório:

1. Identificar com o proprietário a origem que atende o site e conceder leitura
   por canal seguro. Não colocar URI, chave ou dados reais em GitHub/artefatos.
2. Executar `mongo_backup.capture(source_db, destination, recovery_phrase)` fora
   do repositório, com arquivo privado. Requer MongoDB 5+ com snapshot sessions.
   A captura lê todos os documentos sem limite de datas; mudanças de catálogo
   ou índices interrompem a publicação. PyMongo 4.5 está fixado porque o timestamp
   da sessão usa seu atributo privado `_snapshot_time`; atualização exige testes.
3. Executar `validate_restore(path, phrase, isolated_db)`: somente loopback,
   banco vazio `ganoh_restore_test_*`, Mongo descartável iniciado com
   `--setParameter ttlMonitorEnabled=false`. A função não altera esse parâmetro.
   Compara BSON, contagens e índices; falhas deixam o destino em quarentena.
4. Passar o comprovante retornado para `unit_export.export_unit(...,
   validated_backup=receipt)`. Ele vincula o ensaio ao hash do arquivo exato.
   Coleções desconhecidas e registros financeiros sem unidade exigem revisão.
5. Importar somente o pacote da unidade com `desktop.legacy_data.import_bundle`.
   Exige SQLCipher; checkpoint persistente, versões imutáveis e publicação atômica.
   O backup integral inclui configurações privadas: NUNCA distribuir a funcionários.
   Use chave distinta para cada pacote. Não enviar arquivos ou senhas por links públicos.

Arquivos são BSON paginado com AES-GCM, scrypt, autenticação do formato e caminho,
manifesto criptografado e publicação sem sobrescrever destinos existentes. Isso
não substitui custódia/recuperação de chaves, retenção e backups externos testados.

O histórico importado é um cache fiel, não um lançamento contábil novo. Não cria
vendas, fila ou recebimentos. O perfil sobe para schema 4, rejeitado por versões
antigas; novas operações ficam bloqueadas após iniciar a carga até conciliar os
saldos operacionais. A conciliação ainda NÃO está implementada. Não preencher
`legacy_operational_baseline` manualmente para contornar essa proteção.

Faltam acesso confirmado à origem real, reconciliação, atualização incremental
após o snapshot, transporte autenticado, integração com telas originais e ensaio
no Windows. Portanto esta infraestrutura não torna o aplicativo pronto para uso.

Testes isolados (Mongo de ensaio, jamais produção):

```
python -m unittest discover -s backend/data_bridge/tests -v
python -m unittest discover -s desktop/tests -p 'test_*.py' -v
```
