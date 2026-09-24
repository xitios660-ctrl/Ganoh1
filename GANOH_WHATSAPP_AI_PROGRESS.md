# GANOH WhatsApp + IA — Progresso

Branch de trabalho: `ganoh/whatsapp-ai`

## Estado atual

- Produção não foi alterada por esta frente.
- `MIGRATION_PENDING`, `SCHEDULER_ENABLED` e `WHATSAPP_SEND_ENABLED` continuam como travas de segurança.
- Baileys é o provedor planejado. Meta API oficial não faz parte desta implementação.
- A integração de IA usa `OPENAI_API_KEY` somente no servidor e `OPENAI_MODEL` / `OPENAI_VISION_MODEL` para seleção de modelo.
- Nenhuma chave OpenAI foi gravada no repositório.
- O repositório está público. Uma credencial legada de WhatsApp/Green API existia hard-coded na linha histórica/main. Nesta branch o uso hard-coded foi removido, mas a credencial antiga precisa ser rotacionada fora do código antes de qualquer uso futuro.

## Implementado

### Baileys / sessão / entrada de mensagens
- Sessão Baileys persistente e criptografada no MongoDB.
- Lease de sessão para impedir duas instâncias concorrentes.
- QR Code não é registrado em log.
- Mensagens de clientes não são registradas em log.
- Reconexão automática.
- Listener `messages.upsert`.
- Normalização de texto, imagem e documento.
- Ignora mensagens enviadas pelo próprio bot e broadcasts de status.
- Inbox persistente `whatsapp_inbox` com deduplicação por ID da mensagem.
- Retentativa de entrega interna para o backend.
- Bridge interno protegido por `WHATSAPP_INTERNAL_TOKEN`.

### Mídia / comprovantes
- Imagem/PDF suportados para comprovante.
- Tipos aceitos: JPEG, PNG, WEBP e PDF.
- Limite de mídia: 8 MB.
- Mídia armazenada temporariamente de forma criptografada no MongoDB.
- TTL automático de 7 dias para a mídia.
- Backend guarda metadados/análise, não a mídia bruta.
- Hash SHA-256 para detectar comprovante repetido.
- Cliente em conversa privada pode enviar comprovante sem ganhar acesso à IA financeira.
- Grupos não autorizados não podem injetar comprovantes.
- Rate limit básico de comprovantes por remetente.
- Cliente conhecido pode ter análise automática quando a OpenAI estiver configurada.
- Número desconhecido entra na fila e pode ser analisado pelo Gestor.
- Nunca há aprovação financeira automática pela IA.

### OpenAI / IA financeira
- Integração direta via OpenAI Responses API.
- Chaves somente por variável de ambiente.
- IA financeira em modo somente leitura.
- Consultas suportadas sobre vendas, formas de pagamento, prazo, pagamentos de prazo, estoque e resumo.
- Os valores são consultados no Ganoh antes da resposta.
- Pedidos de alteração financeira via WhatsApp são bloqueados e direcionados para confirmação no Gestor.
- Fontes de consulta usam endpoints já existentes do Ganoh.

### Comprovantes no Gestor
- Fila de comprovantes dentro da aba WhatsApp.
- Mostra valor, pagador, confiança e data/hora extraídos quando disponíveis.
- Prévia de imagem/PDF somente sob demanda.
- Botão `Analisar com IA` quando necessário.
- Busca pedidos PIX pendentes compatíveis pelo valor.
- Ações do Gestor: Corrigir, Recusar e Confirmar pagamento.
- Correção de valor recalcula os pedidos compatíveis.
- Confirmação exige pedido PIX ainda em `pending_payment`.
- Valor precisa bater com o pedido (tolerância de R$ 0,01).
- Mesmo comprovante confirmado não pode ser usado novamente.
- Ao confirmar, origem é registrada como `whatsapp_receipt`.
- O fluxo reutiliza a aprovação existente do Ganoh para preservar as regras atuais de pedido/estoque.

### Interface WhatsApp no Gestor
- Estados visuais para conectado, desconectado, aguardando QR, conectando, reconectando, sessão encerrada, conflito e offline.
- QR Code centralizado e responsivo.
- Estado da IA: configurada / pendente.
- Grupo oficial selecionável e persistente.
- Horários 14:00 e 22:00 exibidos.
- Banner de segurança enquanto envio está bloqueado.
- Fila de comprovantes responsiva e integrada à aba WhatsApp.

### Relatórios 14:00 / 22:00
- Mantidos no fuso `America/Sao_Paulo`.
- Trava persistente por data/tipo/loja contra envio duplicado.
- Falha de envio pode ser tentada novamente.
- Claim preso por queda do processo pode ser recuperado depois de 15 minutos.

### Segurança
- Removido nesta branch o uso de credencial legada hard-coded.
- Nenhum segredo novo foi gravado no código.
- Fonte financeira continua sendo o banco, não a memória da IA.
- A IA não altera PIX, caixa, dívida, estoque ou histórico sozinha.
- Revisão humana obrigatória para comprovante.
- Produção continua bloqueada até conclusão da migração e validação de sessão real.

## Testes

CI isolado executado em branch descartável sem deploy de produção.

Última execução validada:
- Backend Python: SUCCESS
  - compilação de `backend/server.py`
  - compilação de `backend/routers/whatsapp_ai.py`
  - testes unitários do WhatsApp/IA
- WhatsApp Node/Baileys: SUCCESS
  - instalação
  - verificação de sintaxe de `server.mjs`
  - testes Node
- Frontend Gestor: SUCCESS
  - instalação
  - build de produção

Existem avisos antigos de dependências de hooks React em páginas já existentes, mas o build conclui com sucesso.

## Ainda pendente antes de produção

1. Rotacionar a credencial legada que ficou exposta no histórico público do repositório.
2. Configurar `OPENAI_API_KEY` de forma secreta no ambiente escolhido.
3. Validar QR Code com uma sessão WhatsApp real em ambiente controlado.
4. Validar persistência/reconexão depois de reinício real do container.
5. Validar um comprovante real de teste ponta a ponta no Gestor, sem valor financeiro real.
6. Validar os relatórios 14:00 e 22:00 com destino de teste.
7. Concluir e validar a migração/sincronização da branch `ganoh/continuity-sync`.
8. Confirmar contagens e idempotência do MongoDB de destino.
9. Revisar o diff final contra `main`.
10. Somente depois considerar merge/deploy.

## Regra de deploy

Não fazer merge na `main`, não liberar `WHATSAPP_SEND_ENABLED`, não remover `MIGRATION_PENDING` e não ativar scheduler em produção antes das validações acima.
