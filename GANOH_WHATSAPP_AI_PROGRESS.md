# GANOH WhatsApp + IA — Progresso

Branch de trabalho: `ganoh/whatsapp-ai`

## Estado atual

- Produção não alterada.
- `MIGRATION_PENDING`, `SCHEDULER_ENABLED` e `WHATSAPP_SEND_ENABLED` permanecem como travas de segurança.
- Baileys continua sendo o provedor planejado; Meta API oficial não faz parte desta frente.
- A chave da OpenAI não é armazenada no repositório. A integração usa `OPENAI_API_KEY` no servidor e `OPENAI_MODEL` para seleção de modelo.
- Foi removido, nesta branch, o uso de uma credencial legada de WhatsApp hard-coded. Como o repositório está público e o valor existiu no histórico, essa credencial antiga deve ser rotacionada fora do código antes de qualquer uso futuro.

## Concluído nesta branch

- Normalização segura de mensagens recebidas do Baileys.
- Ignora mensagens enviadas pelo próprio bot e broadcasts de status.
- Fila persistente `whatsapp_inbox` no MongoDB.
- Deduplicação por ID de mensagem.
- Retentativa de entrega interna sem registrar conteúdo sensível em logs.
- Bridge interno `/api/whatsapp/internal/incoming` protegido por `WHATSAPP_INTERNAL_TOKEN`.
- Assistente financeiro somente leitura.
- Allowlist por grupo oficial/JIDs autorizados.
- Consultas de vendas, prazo, pagamentos de prazo e estoque usando dados reais do Ganoh.
- Bloqueio explícito de pedidos de alteração financeira via WhatsApp.
- Integração OpenAI via Responses API, com fallback seguro quando a chave não está configurada.
- Estado da IA exposto ao Gestor.
- Aba WhatsApp revisada para QR Code, status, IA, grupo oficial e relatórios 14:00/22:00.
- Trava persistente contra relatórios duplicados por loja/data/horário.
- Testes unitários adicionados para normalização de mensagens e guardrails da IA.

## Ainda pendente

- Executar CI completo da branch.
- Implementar download/validação de mídia para comprovantes recebidos no WhatsApp.
- Criar fluxo de confirmação/correção/recusa de comprovante no Gestor.
- Validar QR Code em ambiente de teste com sessão real sem liberar envio.
- Configurar `OPENAI_API_KEY` somente após validação e sem expor o valor.
- Validar relatórios 14:00 e 22:00 com banco de teste/produção protegida.
- Revisar integração com a frente `ganoh/continuity-sync` sem misturar branches.
- Comparar diff completo contra `main` antes de qualquer merge/deploy.

## Regra de deploy

Não fazer merge na `main` nem deploy em produção até os testes passarem e os dados migrados estarem validados.
