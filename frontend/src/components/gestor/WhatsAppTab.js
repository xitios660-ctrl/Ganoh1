import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  Clock3,
  Eye,
  Loader2,
  MessageCircle,
  Pencil,
  QrCode,
  Receipt,
  RefreshCw,
  ShieldCheck,
  Users,
  WifiOff,
  XCircle
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

const STATUS_COPY = {
  connected: { label: 'Conectado', hint: 'Sessão ativa e persistente', dot: 'bg-green-500' },
  waiting_qr: { label: 'Aguardando QR Code', hint: 'Escaneie o código abaixo', dot: 'bg-yellow-500 animate-pulse' },
  connecting: { label: 'Conectando', hint: 'Preparando a sessão do WhatsApp', dot: 'bg-blue-500 animate-pulse' },
  reconnecting: { label: 'Reconectando', hint: 'Tentando recuperar a sessão automaticamente', dot: 'bg-blue-500 animate-pulse' },
  logged_out: { label: 'Sessão encerrada', hint: 'Será necessário conectar novamente', dot: 'bg-orange-500' },
  connection_conflict: { label: 'Conflito de sessão', hint: 'A sessão pode estar aberta em outro serviço', dot: 'bg-orange-500' },
  offline: { label: 'Serviço indisponível', hint: 'O serviço do bot não respondeu', dot: 'bg-red-500' },
  disconnected: { label: 'Desconectado', hint: 'Conecte o WhatsApp para iniciar', dot: 'bg-red-500' },
};

const authConfig = () => {
  const value = localStorage.getItem('gestor_auth');
  return { headers: value ? { Authorization: `Basic ${value}` } : {}, timeout: 20000 };
};

const money = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 'Valor não identificado';
  return parsed.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const receiptDraft = (receipt) => ({
  amount: receipt?.analysis?.amount ?? '',
  payer_name: receipt?.analysis?.payer_name ?? '',
  order_id:
    receipt?.selected_order_id ||
    (receipt?.candidate_orders?.length === 1 ? receipt.candidate_orders[0].id : ''),
  notes: receipt?.notes || ''
});

export function WhatsAppTab({
  whatsappStatus,
  whatsappQR,
  whatsappGroups,
  whatsappTarget,
  whatsappTargetInput,
  setWhatsappTargetInput,
  onJoinGroup,
  onConnect,
  onSaveTarget,
  sendingEnabled,
  aiConfigured,
  aiModel,
  onRefreshStatus
}) {
  const status = STATUS_COPY[whatsappStatus] || STATUS_COPY.disconnected;
  const isBusy = whatsappStatus === 'connecting' || whatsappStatus === 'reconnecting';
  const canConnect = whatsappStatus !== 'connected' && !isBusy;

  const [receipts, setReceipts] = useState([]);
  const [receiptDrafts, setReceiptDrafts] = useState({});
  const [receiptMedia, setReceiptMedia] = useState({});
  const [receiptsLoading, setReceiptsLoading] = useState(false);
  const [receiptActionId, setReceiptActionId] = useState('');

  const refreshReceipts = useCallback(async (silent = false) => {
    if (!silent) setReceiptsLoading(true);
    try {
      const response = await axios.get(`${API}/whatsapp/receipts?limit=50`, authConfig());
      const items = response.data.receipts || [];
      setReceipts(items);
      setReceiptDrafts((current) => {
        const next = { ...current };
        items.forEach((item) => {
          if (!next[item.id]) next[item.id] = receiptDraft(item);
        });
        return next;
      });
    } catch (error) {
      if (!silent && error?.response?.status !== 404) {
        toast.error('Não foi possível carregar os comprovantes do WhatsApp.');
      }
    } finally {
      if (!silent) setReceiptsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshReceipts(true);
    const timer = setInterval(() => refreshReceipts(true), 15000);
    return () => clearInterval(timer);
  }, [refreshReceipts]);

  const updateReceiptDraft = (id, field, value) => {
    setReceiptDrafts((current) => ({
      ...current,
      [id]: { ...(current[id] || {}), [field]: value }
    }));
  };

  const loadReceiptMedia = async (receipt) => {
    if (receiptMedia[receipt.id]) {
      setReceiptMedia((current) => {
        const next = { ...current };
        delete next[receipt.id];
        return next;
      });
      return;
    }
    setReceiptActionId(`media:${receipt.id}`);
    try {
      const response = await axios.get(`${API}/whatsapp/receipts/${receipt.id}/media`, authConfig());
      setReceiptMedia((current) => ({ ...current, [receipt.id]: response.data }));
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'A mídia do comprovante não está mais disponível.');
    } finally {
      setReceiptActionId('');
    }
  };

  const analyzeReceipt = async (receipt) => {
    setReceiptActionId(`analyze:${receipt.id}`);
    try {
      await axios.post(`${API}/whatsapp/receipts/${receipt.id}/analyze`, {}, authConfig());
      toast.success('Comprovante analisado. Confira os dados antes de confirmar.');
      setReceiptDrafts((current) => {
        const next = { ...current };
        delete next[receipt.id];
        return next;
      });
      await refreshReceipts(true);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Não foi possível analisar o comprovante.');
    } finally {
      setReceiptActionId('');
    }
  };

  const reviewReceipt = async (receipt, action) => {
    const draft = receiptDrafts[receipt.id] || receiptDraft(receipt);
    if (action === 'confirm' && !draft.order_id) {
      toast.error('Selecione o pedido PIX antes de confirmar.');
      return;
    }
    if ((action === 'confirm' || action === 'correct') && draft.amount === '') {
      toast.error('Confira o valor do comprovante.');
      return;
    }

    setReceiptActionId(`${action}:${receipt.id}`);
    try {
      await axios.post(
        `${API}/whatsapp/receipts/${receipt.id}/review`,
        {
          action,
          order_id: draft.order_id || null,
          amount: draft.amount === '' ? null : Number(draft.amount),
          payer_name: draft.payer_name || null,
          notes: draft.notes || null
        },
        authConfig()
      );

      if (action === 'confirm') toast.success('Comprovante confirmado pelo Gestor.');
      if (action === 'reject') toast.success('Comprovante recusado.');
      if (action === 'correct') toast.success('Correção salva e pedidos compatíveis recalculados.');

      setReceiptDrafts((current) => {
        const next = { ...current };
        delete next[receipt.id];
        return next;
      });
      await refreshReceipts(true);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Não foi possível concluir a revisão.');
    } finally {
      setReceiptActionId('');
    }
  };

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <MessageCircle className="h-5 w-5 text-green-600" />
                WhatsApp & IA
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Conexão Baileys, assistente financeiro e relatórios do Ganoh.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={onRefreshStatus}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Atualizar
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border bg-secondary/20 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <MessageCircle className="h-4 w-4" />
                WhatsApp
              </div>
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${status.dot}`} />
                <span className="font-semibold">{status.label}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{status.hint}</p>
            </div>

            <div className="rounded-xl border bg-secondary/20 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Bot className="h-4 w-4" />
                IA
              </div>
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${aiConfigured ? 'bg-green-500' : 'bg-yellow-500'}`} />
                <span className="font-semibold">{aiConfigured ? 'Configurada' : 'Configuração pendente'}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {aiConfigured ? `${aiModel || 'OpenAI'} · somente leitura financeira` : 'Aguardando chave segura no servidor'}
              </p>
            </div>

            <div className="rounded-xl border bg-secondary/20 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Clock3 className="h-4 w-4" />
                Relatórios
              </div>
              <div className="font-semibold">14:00 · 22:00</div>
              <p className="mt-1 text-xs text-muted-foreground">Horário de São Paulo</p>
            </div>
          </div>

          {!sendingEnabled && (
            <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <p className="font-medium">Envio protegido durante a migração</p>
                <p className="mt-1 text-sm text-amber-800">
                  O WhatsApp pode ser preparado e testado, mas mensagens automáticas continuam bloqueadas até a validação final dos dados.
                </p>
              </div>
            </div>
          )}

          {whatsappQR && whatsappStatus !== 'connected' && (
            <div className="rounded-2xl border bg-gradient-to-b from-white to-slate-50 p-5 text-center shadow-sm">
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-green-100 text-green-700">
                <QrCode className="h-5 w-5" />
              </div>
              <h3 className="font-semibold text-slate-900">Conectar WhatsApp</h3>
              <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">
                No celular, abra WhatsApp → Configurações → Aparelhos conectados e escaneie o código.
              </p>
              <div className="mx-auto mt-5 w-fit rounded-2xl border bg-white p-3 shadow-sm">
                <img
                  src={`data:image/png;base64,${whatsappQR}`}
                  alt="QR Code para conectar o WhatsApp ao Ganoh"
                  className="h-56 w-56 max-w-[70vw]"
                />
              </div>
              <p className="mt-3 text-xs text-slate-400">
                A sessão será armazenada de forma persistente para evitar novo QR a cada reinício.
              </p>
            </div>
          )}

          {!whatsappQR && canConnect && (
            <div className="rounded-xl border bg-secondary/20 p-5 text-center">
              <QrCode className="mx-auto h-8 w-8 text-muted-foreground" />
              <p className="mt-3 font-medium">
                {whatsappStatus === 'offline' ? 'Serviço do WhatsApp não respondeu' : 'WhatsApp ainda não conectado'}
              </p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {whatsappStatus === 'offline'
                  ? 'Atualize o status. Quando o serviço estiver disponível, gere um novo QR Code.'
                  : 'Gere o QR Code para vincular o aparelho ao Ganoh.'}
              </p>
              <Button
                onClick={whatsappStatus === 'offline' ? onRefreshStatus : onConnect}
                className="mt-4 bg-green-600 hover:bg-green-700"
              >
                {whatsappStatus === 'offline' ? (
                  <><RefreshCw className="mr-2 h-4 w-4" /> Verificar serviço</>
                ) : (
                  <><QrCode className="mr-2 h-4 w-4" /> Gerar QR Code</>
                )}
              </Button>
            </div>
          )}

          {isBusy && (
            <div className="rounded-xl border bg-blue-50 p-4 text-center text-sm text-blue-800">
              <RefreshCw className="mr-2 inline h-4 w-4 animate-spin" />
              {status.hint}
            </div>
          )}

          {whatsappStatus === 'connected' && (
            <div className="space-y-4">
              <div className="flex gap-3 rounded-xl border border-green-200 bg-green-50 p-4 text-green-900">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
                <div>
                  <p className="font-medium">WhatsApp conectado</p>
                  <p className="mt-1 text-sm text-green-800">
                    Sessão protegida, persistente e com reconexão automática.
                  </p>
                </div>
              </div>

              <div className="rounded-xl border bg-secondary/20 p-4">
                <Label className="mb-2 flex items-center gap-2 font-medium">
                  <Users className="h-4 w-4" />
                  Grupo oficial do Ganoh
                </Label>
                <p className="mb-3 text-xs text-muted-foreground">
                  Selecione um grupo listado abaixo ou cole um link de convite.
                </p>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={whatsappTargetInput}
                    onChange={(e) => setWhatsappTargetInput(e.target.value)}
                    placeholder="Grupo selecionado ou link chat.whatsapp.com/..."
                    className="flex-1"
                  />
                  <Button
                    onClick={whatsappTargetInput.includes('chat.whatsapp.com') ? onJoinGroup : onSaveTarget}
                    className="bg-green-600 hover:bg-green-700"
                    disabled={!whatsappTargetInput.trim()}
                  >
                    {whatsappTargetInput.includes('chat.whatsapp.com') ? 'Entrar no grupo' : 'Salvar grupo'}
                  </Button>
                </div>
                {whatsappTarget && (
                  <p className="mt-2 break-all text-xs text-muted-foreground">
                    <ShieldCheck className="mr-1 inline h-3.5 w-3.5" />
                    Destino salvo: <code>{whatsappTarget}</code>
                  </p>
                )}
              </div>

              {whatsappGroups.length > 0 && (
                <div className="rounded-xl border bg-secondary/20 p-4">
                  <Label className="mb-3 flex items-center gap-2 font-medium">
                    <MessageCircle className="h-4 w-4" />
                    Grupos disponíveis
                  </Label>
                  <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                    {whatsappGroups.map((group) => (
                      <button
                        type="button"
                        key={group.id}
                        className="flex w-full items-center justify-between gap-3 rounded-lg border bg-background p-3 text-left text-sm transition hover:bg-secondary/50"
                        onClick={() => {
                          setWhatsappTargetInput(group.id);
                          toast.info(`Grupo "${group.name}" selecionado. Clique em Salvar grupo.`);
                        }}
                      >
                        <span className="font-medium">{group.name}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {group.participants} membros
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {whatsappStatus === 'offline' && (
            <div className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-900">
              <WifiOff className="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <p className="font-medium">Bot indisponível</p>
                <p className="mt-1 text-sm text-red-800">
                  Nenhuma sessão ou dado financeiro será apagado. Verifique o serviço antes de tentar conectar novamente.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Receipt className="h-5 w-5" />
                Comprovantes aguardando revisão
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                A IA extrai os dados, mas somente o Gestor pode confirmar o pagamento.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => refreshReceipts(false)} disabled={receiptsLoading}>
              {receiptsLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Revisar
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {receipts.length === 0 ? (
            <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              Nenhum comprovante pendente no momento.
            </div>
          ) : (
            <div className="space-y-4">
              {receipts.map((receipt) => {
                const draft = receiptDrafts[receipt.id] || receiptDraft(receipt);
                const media = receiptMedia[receipt.id];
                const candidates = receipt.candidate_orders || [];
                const duplicate = receipt.status === 'duplicate_suspected';
                const busy = receiptActionId.endsWith(`:${receipt.id}`);

                return (
                  <div key={receipt.id} className="rounded-2xl border bg-background p-4 shadow-sm">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{money(receipt.analysis?.amount)}</span>
                          <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                            {receipt.analysis?.analysis_status === 'analyzed'
                              ? 'Analisado pela IA'
                              : receipt.analysis?.analysis_status === 'analysis_failed'
                                ? 'Falha na análise'
                                : 'Aguardando análise'}
                          </span>
                          {duplicate && (
                            <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">
                              <AlertTriangle className="h-3 w-3" />
                              Possível duplicado
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Pagador: {receipt.analysis?.payer_name || 'não identificado'}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Confiança: {Math.round(Number(receipt.analysis?.confidence || 0) * 100)}%
                          {receipt.analysis?.transaction_date ? ` · ${receipt.analysis.transaction_date}` : ''}
                          {receipt.analysis?.transaction_time ? ` ${receipt.analysis.transaction_time}` : ''}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {receipt.analysis?.analysis_status !== 'analyzed' && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => analyzeReceipt(receipt)}
                            disabled={!aiConfigured || busy}
                          >
                            {receiptActionId === `analyze:${receipt.id}`
                              ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              : <Bot className="mr-2 h-4 w-4" />}
                            {aiConfigured ? 'Analisar com IA' : 'IA não configurada'}
                          </Button>
                        )}
                        <Button variant="outline" size="sm" onClick={() => loadReceiptMedia(receipt)}>
                          {receiptActionId === `media:${receipt.id}`
                            ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            : <Eye className="mr-2 h-4 w-4" />}
                          {media ? 'Ocultar' : 'Ver comprovante'}
                        </Button>
                      </div>
                    </div>

                    {media && (
                      <div className="mt-4 rounded-xl border bg-secondary/10 p-3">
                        {media.mimeType?.startsWith('image/') ? (
                          <img
                            src={`data:${media.mimeType};base64,${media.data}`}
                            alt="Comprovante recebido pelo WhatsApp"
                            className="mx-auto max-h-96 max-w-full rounded-lg object-contain"
                          />
                        ) : (
                          <a
                            href={`data:${media.mimeType || 'application/pdf'};base64,${media.data}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-sm font-medium underline"
                          >
                            Abrir documento {media.fileName || 'comprovante'}
                          </a>
                        )}
                      </div>
                    )}

                    <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <Label className="text-xs">Valor conferido</Label>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={draft.amount}
                          onChange={(e) => updateReceiptDraft(receipt.id, 'amount', e.target.value)}
                          placeholder="0,00"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Nome do pagador</Label>
                        <Input
                          value={draft.payer_name}
                          onChange={(e) => updateReceiptDraft(receipt.id, 'payer_name', e.target.value)}
                          placeholder="Pagador"
                        />
                      </div>
                    </div>

                    <div className="mt-3">
                      <Label className="text-xs">Pedido PIX correspondente</Label>
                      <select
                        className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                        value={draft.order_id}
                        onChange={(e) => updateReceiptDraft(receipt.id, 'order_id', e.target.value)}
                      >
                        <option value="">Selecione o pedido</option>
                        {candidates.map((order) => (
                          <option key={order.id} value={order.id}>
                            {order.customer_name || 'Cliente'} · {money(order.total)} · {order.store}
                          </option>
                        ))}
                      </select>
                      {candidates.length === 0 && (
                        <p className="mt-1 text-xs text-amber-700">
                          Nenhum pedido PIX pendente bateu com esse valor. Corrija o valor e salve antes de confirmar.
                        </p>
                      )}
                    </div>

                    <div className="mt-3">
                      <Label className="text-xs">Observação do Gestor</Label>
                      <Input
                        value={draft.notes}
                        onChange={(e) => updateReceiptDraft(receipt.id, 'notes', e.target.value)}
                        placeholder="Opcional"
                      />
                    </div>

                    <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
                      <Button
                        variant="outline"
                        onClick={() => reviewReceipt(receipt, 'correct')}
                        disabled={busy}
                      >
                        {receiptActionId === `correct:${receipt.id}`
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <Pencil className="mr-2 h-4 w-4" />}
                        Corrigir
                      </Button>
                      <Button
                        variant="outline"
                        className="border-red-200 text-red-700 hover:bg-red-50"
                        onClick={() => reviewReceipt(receipt, 'reject')}
                        disabled={busy}
                      >
                        {receiptActionId === `reject:${receipt.id}`
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <XCircle className="mr-2 h-4 w-4" />}
                        Recusar
                      </Button>
                      <Button
                        className="bg-green-600 hover:bg-green-700"
                        onClick={() => reviewReceipt(receipt, 'confirm')}
                        disabled={busy || !draft.order_id}
                      >
                        {receiptActionId === `confirm:${receipt.id}`
                          ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          : <Check className="mr-2 h-4 w-4" />}
                        Confirmar pagamento
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default WhatsAppTab;
