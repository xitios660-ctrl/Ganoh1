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

## Matriz atual — incremento 0.4.0

| Área | Implementado e testado em ambiente isolado | Pendente para paridade |
| --- | --- | --- |
| Vendas/cardápio | Dinheiro e prazo aprovado, catálogo local editável, reservas e UUID estável | Telas originais completas, adicionais, categorias, cancelamento/estorno |
| Caixa | Abertura, fechamento, diferença bloqueada para revisão, reconciliação com motivo e conta de diferença | Relatórios legados e homologação financeira física |
| Despesas/clientes | Despesa em dinheiro, cadastro, limite versionado e permissão de proprietário | Demais campos, edição completa e download de clientes/saldos centrais |
| Prazo | Aprovação central obrigatória do limite, venda, recebimento parcial, recibo único | Estornos, demais meios e histórico legado |
| Estoque | Projeção/reserva offline, entrada/ajuste versionado, snapshot paginado com cobertura por hash | Revisão visual e reversões completas; limite demonstrativo 1.000 SKUs |
| Cozinha | Fila local e transições versionadas até entrega, perfil sem valores financeiros | Paridade visual/tempos/histórico da cozinha original |
| Proprietário | Painel separado com login, valores centrais confirmados por unidade, atraso e estoque paginado | Hospedagem HTTPS de homologação, relatórios legados e UI de revisão de conflitos |
| Segurança | SQLCipher, DPAPI, contas owner/cashier/kitchen, scrypt, sessões revogáveis e auditoria local | Provisionamento real e validação externa; identidade do operador não atestada centralmente |
| Backup/relatórios | Backup cifrado consistente, chave recuperável por frase, restauração isolada, CSV provisório | Ativação segura da recuperação, retenção automática e relatório/PDF legado |
| PIX/cartão/WhatsApp | Sistema web existente preservado | Adaptadores online e confirmação válida; sem liquidação offline simulada |
| Windows | Electron/PyInstaller/NSIS, atalho, backend oculto e dados fora da instalação | Testes físicos Win10/11, dois PCs, upgrade entre versões, assinatura e rollback |

A tela operacional reutiliza tema/componentes, mas não é a reprodução integral das telas originais. Não importar dados reais nem substituir o site. Snapshots atuais cobrem catálogo/estoque; clientes e saldos alterados remotamente não são baixados automaticamente. Divergências financeiras exigem revisão; não há aprovação silenciosa.

O painel novo lê somente o livro da central isolada `ganoh_sync_test_*`. Não recebe dados de produção, e não conhece vendas ainda offline: pendências locais remotas são explicitamente desconhecidas. O acesso atual pelo celular permanece no site existente.

Evidências e contagens atualizadas: [relatório técnico](CODEX_WINDOWS_PROGRESS_2026-11-18.md). Não declarar paridade completa ou homologação comercial com base apenas na CI.
