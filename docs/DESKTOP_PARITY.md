# Paridade Windows — inventário de evolução

O aplicativo deve atingir as funções do site antes de substituir qualquer atendimento. Este inventário foi extraído por AST de `backend/server.py`, sem importar o servidor ou acessar MongoDB/Render. Os grupos abaixo não incluem automaticamente todas as rotas de roteadores auxiliares. Contar rotas não comprova paridade.

| Grupo de rotas existente | Quantidade em server.py |
| --- | ---: |
| `/` | 1 |
| `admin` | 17 |
| `auth` | 4 |
| `cash` | 7 |
| `categories` | 1 |
| `expenses` | 8 |
| `gestor` | 25 |
| `kitchen` | 12 |
| `menu` | 1 |
| `orders` | 14 |
| `pix` | 1 |
| `pix-adjustments` | 3 |
| `prazo` | 17 |
| `staff` | 1 |
| `stock` | 5 |
| `stores` | 1 |
| `whatsapp` | 15 |

## Matriz de implementação local

| Área | Implementação local atual | Pendente para paridade |
| --- | --- | --- |
| Cardápio e vendas | Snapshot de catálogo, venda em dinheiro, fila/recibo idempotentes | Cardápio original completo, adicionais/categorias, cancelamentos/estornos e formas de pagamento |
| Caixa | Livro em centavos, venda em dinheiro, suprimento, retirada e bloqueio de saldo insuficiente | Abertura/fechamento por turno, conferência, diferenças auditadas, permissões individuais e relatórios legados |
| Despesas | Registro de despesa em dinheiro com lançamento/outbox atômicos | Categorias e demais meios, ajustes/estornos e telas do gestor original |
| Clientes | Cadastro local e sync por unidade, dedupe de UUID e nome normalizado | Edição versionada, telefones/demais campos, snapshots e busca compatíveis com legado |
| Prazo | Motor de recebimento em dinheiro contra dívida existente, recibo único e bloqueio de excedente | Vendas a prazo, limites aprovados, crédito/estornos, snapshots históricos e conciliação; clientes novos começam sem dívida |
| Estoque | Snapshot/versionamento e conflitos centrais | Reserva/projeção offline de múltiplas vendas, ajustes/entradas/perdas, revisão/reversões e tela original |
| Cozinha | Interface web preservada | Endpoints locais para fila/status/tempo/histórico e testes de paridade |
| Gestor/relatórios | Site remoto atual preservado; resumo local demonstrativo provisório | Integração do livro financeiro com relatórios, gráficos/PDF/CSV, consolidado e indicador remoto de atraso |
| Autenticação | Sessão loopback, dispositivo revogável, DPAPI/SQLCipher | Papéis individuais/credenciais offline, provisionamento e recuperação segura |
| PIX/cartão/WhatsApp | Integrações do site preservadas, sem liquidação automática offline | Adaptadores online seguros e confirmação válida, sem prometer banco/WhatsApp offline |
| Windows | Electron/PyInstaller/NSIS, persistência e testes de reinstalação | Homologação interativa Win10/11, atualização entre versões, assinatura, backup/restauração e recuperação de chave |

Cada módulo exige testes de regras e equivalência antes de ser marcado pronto. A nova demonstração não importa dados reais, não substitui as telas web atuais e não alimenta os relatórios de produção. Recebimentos contra dívida só podem ser demonstrados com fixtures fictícias enquanto snapshots de clientes/dívidas ainda não estiverem implementados. Não fabricar saldo nem copiar dados de produção sem backup/restauração e autorização.
