import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  MessageCircle,
  Users,
  RefreshCw,
  CheckCircle2,
  Shield,
  Bot,
  Clock,
  AlertTriangle,
  QrCode
} from 'lucide-react';
import { toast } from 'sonner';

const STATUS_META = {
  connected: {
    label: 'Conectado',
    detail: 'Sessão ativa e persistente',
    dot: 'bg-green-500',
    badge: 'bg-green-50 text-green-800 border-green-200'
  },
  disconnected: {
    label: 'Desconectado',
    detail: 'Nenhuma sessão ativa',
    dot: 'bg-red-500',
    badge: 'bg-red-50 text-red-800 border-red-200'
  },
  connecting: {
    label: 'Conectando',
    detail: 'Iniciando sessão Baileys…',
    dot: 'bg-blue-500 animate-pulse',
    badge: 'bg-blue-50 text-blue-800 border-blue-200'
  },
  waiting_qr: {
    label: 'Aguardando QR',
    detail: 'Escaneie o código com o celular',
    dot: 'bg-yellow-500 animate-pulse',
    badge: 'bg-yellow-50 text-yellow-800 border-yellow-200'
  },
  reconnecting: {
    label: 'Reconectando',
    detail: 'Tentando restaurar a sessão…',
    dot: 'bg-blue-500 animate-pulse',
    badge: 'bg-blue-50 text-blue-800 border-blue-200'
  },
  logged_out: {
    label: 'Sessão encerrada',
    detail: 'Conecte novamente pelo QR Code',
    dot: 'bg-orange-500',
    badge: 'bg-orange-50 text-orange-800 border-orange-200'
  },
  connection_conflict: {
    label: 'Conflito de conexão',
    detail: 'Sessão em uso em outro serviço',
    dot: 'bg-amber-500',
    badge: 'bg-amber-50 text-amber-900 border-amber-200'
  },
  offline: {
    label: 'Serviço offline',
    detail: 'Bot WhatsApp indisponível no servidor',
    dot: 'bg-red-500',
    badge: 'bg-red-50 text-red-800 border-red-200'
  }
};

function formatDateTime(value) {
  if (!value) return '—';
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  } catch {
    return '—';
  }
}

export function WhatsAppTab({
  whatsappStatus,
  whatsappQR,
  whatsappGroups = [],
  whatsappTarget,
  whatsappTargetInput,
  setWhatsappTargetInput,
  onJoinGroup,
  onConnect,
  onSaveTarget,
  sendingEnabled,
  onRefreshStatus,
  lastConnectedAt = null,
  lastReportAt = null,
  recentErrors = [],
  aiConfigured = false,
  reportSchedule = ['14:00', '22:00']
}) {
  const meta = STATUS_META[whatsappStatus] || STATUS_META.disconnected;
  const isConnected = whatsappStatus === 'connected';
  const isOffline = whatsappStatus === 'offline';
  const showQr = Boolean(whatsappQR) && !isConnected;
  const showConnectCta =
    !isConnected &&
    !isOffline &&
    !showQr &&
    whatsappStatus !== 'connecting' &&
    whatsappStatus !== 'reconnecting';
  const isInviteLink = (whatsappTargetInput || '').includes('chat.whatsapp.com');
  const scheduleLabel = Array.isArray(reportSchedule) && reportSchedule.length
    ? reportSchedule.join(' / ')
    : '14:00 / 22:00';

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
          <MessageCircle className="h-5 w-5 text-green-600 shrink-0" />
          WhatsApp
        </CardTitle>
        <div className="h-px w-full bg-border mt-2" />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status indicator */}
        <div className={`flex flex-col sm:flex-row sm:items-center gap-3 p-4 rounded-lg border ${meta.badge}`}>
          <div className="flex items-center gap-3 min-w-0">
            <div className={`w-3 h-3 rounded-full shrink-0 ${meta.dot}`} aria-hidden />
            <div className="min-w-0">
              <p className="font-semibold leading-tight">{meta.label}</p>
              <p className="text-xs sm:text-sm opacity-80 truncate">{meta.detail}</p>
            </div>
          </div>
          <div className="sm:ml-auto text-xs sm:text-sm opacity-80">
            Última conexão: {formatDateTime(lastConnectedAt)}
          </div>
        </div>

        {/* Connection card: QR / CTA / connected banner */}
        <div className="rounded-lg border bg-secondary/20 p-4 space-y-4">
          {isConnected && (
            <div className="bg-green-50 p-4 rounded-lg border border-green-200 space-y-2">
              <p className="text-green-800 font-medium flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                WhatsApp conectado
              </p>
              <p className="text-sm text-green-700 flex items-center gap-2">
                <Shield className="h-3.5 w-3.5 shrink-0" />
                Sessão protegida e persistente
              </p>
              <p className="text-xs text-green-700/90">
                {sendingEnabled
                  ? 'Envio de mensagens habilitado.'
                  : 'Conexão pronta. O envio de mensagens permanece desligado até liberação da migração.'}
              </p>
            </div>
          )}

          {showQr && (
            <div className="bg-white p-4 sm:p-6 rounded-lg border text-center space-y-3">
              <p className="text-sm font-medium flex items-center justify-center gap-2">
                <QrCode className="h-4 w-4 text-green-600" />
                Escaneie o QR Code com seu WhatsApp
              </p>
              <div className="mx-auto w-full max-w-[240px]">
                <img
                  src={`data:image/png;base64,${whatsappQR}`}
                  alt="WhatsApp QR Code"
                  className="w-full h-auto aspect-square object-contain rounded-md border bg-white"
                />
              </div>
              <ol className="text-xs text-muted-foreground text-left max-w-sm mx-auto space-y-1 list-decimal list-inside">
                <li>Abra o WhatsApp no celular</li>
                <li>Configurações → Aparelhos conectados</li>
                <li>Toque em Conectar aparelho e escaneie</li>
              </ol>
            </div>
          )}

          {showConnectCta && (
            <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200 text-center space-y-3">
              <p className="text-yellow-800 font-medium">WhatsApp não conectado</p>
              <p className="text-sm text-yellow-700">
                Gere um QR Code para autenticar a sessão Baileys no Gestor.
              </p>
              <div className="flex flex-col sm:flex-row gap-2 justify-center">
                <Button
                  onClick={onConnect || onRefreshStatus}
                  className="bg-green-600 hover:bg-green-700 w-full sm:w-auto"
                >
                  <QrCode className="h-4 w-4 mr-2" />
                  Conectar WhatsApp
                </Button>
                <Button
                  variant="outline"
                  onClick={onConnect || onRefreshStatus}
                  className="w-full sm:w-auto"
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Gerar QR Code
                </Button>
              </div>
            </div>
          )}

          {(whatsappStatus === 'connecting' || whatsappStatus === 'reconnecting') && !showQr && (
            <div className="bg-blue-50 p-4 rounded-lg border border-blue-200 text-center">
              <p className="text-blue-800 font-medium flex items-center justify-center gap-2">
                <RefreshCw className="h-4 w-4 animate-spin" />
                {meta.label}…
              </p>
              <p className="text-sm text-blue-700 mt-1">{meta.detail}</p>
            </div>
          )}

          {isOffline && (
            <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
              <p className="text-yellow-800 font-medium flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                Serviço do bot não está rodando
              </p>
              <p className="text-sm text-yellow-700 mt-2">
                O sidecar WhatsApp precisa estar ativo no servidor. Atualize o status após o serviço subir.
              </p>
            </div>
          )}
        </div>

        {/* Grupo de relatórios — shown when connected */}
        {isConnected && (
          <div className="space-y-4">
            <div className="bg-secondary/30 p-4 rounded-lg border space-y-3">
              <Label className="font-medium flex items-center gap-2">
                <Users className="h-4 w-4" /> Grupo de relatórios
              </Label>
              <p className="text-xs text-muted-foreground">
                Cole o link de convite do grupo ou selecione um grupo da lista e salve como destino.
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <Input
                  value={whatsappTargetInput}
                  onChange={(e) => setWhatsappTargetInput(e.target.value)}
                  placeholder="https://chat.whatsapp.com/xxx ou id@g.us"
                  className="flex-1"
                />
                <Button
                  onClick={isInviteLink ? onJoinGroup : onSaveTarget}
                  className="bg-green-600 hover:bg-green-700 w-full sm:w-auto shrink-0"
                >
                  {isInviteLink ? 'Entrar no grupo' : 'Salvar destino'}
                </Button>
              </div>
              {whatsappTarget ? (
                <p className="text-xs text-muted-foreground break-all">
                  Destino atual:{' '}
                  <code className="bg-secondary px-1 rounded">{whatsappTarget}</code>
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">Nenhum grupo de relatórios configurado.</p>
              )}
            </div>

            {whatsappGroups.length > 0 && (
              <div className="bg-secondary/30 p-4 rounded-lg border">
                <Label className="font-medium flex items-center gap-2 mb-2">
                  <MessageCircle className="h-4 w-4" /> Grupos disponíveis
                </Label>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {whatsappGroups.map((group) => {
                    const selected = whatsappTarget === group.id || whatsappTargetInput === group.id;
                    return (
                      <div
                        key={group.id}
                        role="button"
                        tabIndex={0}
                        className={`flex items-center justify-between gap-2 p-2 rounded border text-sm cursor-pointer ${
                          selected ? 'bg-green-50 border-green-300' : 'bg-white hover:bg-secondary/50'
                        }`}
                        onClick={() => {
                          setWhatsappTargetInput(group.id);
                          toast.info(`Grupo "${group.name}" selecionado. Clique em Salvar destino.`);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setWhatsappTargetInput(group.id);
                            toast.info(`Grupo "${group.name}" selecionado. Clique em Salvar destino.`);
                          }
                        }}
                      >
                        <span className="truncate font-medium">{group.name}</span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {group.participants} membros
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* IA placeholder (ETAPA 6) */}
        <div className="bg-secondary/30 p-4 rounded-lg border">
          <Label className="font-medium flex items-center gap-2 mb-2">
            <Bot className="h-4 w-4" /> IA
          </Label>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`w-2.5 h-2.5 rounded-full ${aiConfigured ? 'bg-green-500' : 'bg-amber-400'}`}
              aria-hidden
            />
            <span>
              {aiConfigured ? 'Chave detectada — configuração pendente (ETAPA 6)' : 'Configuração pendente'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Respostas automáticas e consultas financeiras ainda não estão ativas.
          </p>
        </div>

        {/* Relatórios automáticos (informational) */}
        <div className="bg-secondary/30 p-4 rounded-lg border space-y-2">
          <Label className="font-medium flex items-center gap-2">
            <Clock className="h-4 w-4" /> Relatórios automáticos
          </Label>
          <p className="text-sm">
            Horários planejados: <span className="font-medium">{scheduleLabel}</span>
            <span className="text-muted-foreground"> (America/Sao_Paulo)</span>
          </p>
          <p className="text-xs text-muted-foreground">
            Informativo apenas — o agendador permanece desligado até liberação explícita.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm pt-1">
            <div>
              <span className="text-muted-foreground">Última conexão:</span>{' '}
              <span className="font-medium">{formatDateTime(lastConnectedAt)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Último relatório:</span>{' '}
              <span className="font-medium">{formatDateTime(lastReportAt)}</span>
            </div>
          </div>
        </div>

        {/* Erros recentes (safe) */}
        <div className="bg-secondary/30 p-4 rounded-lg border space-y-2">
          <Label className="font-medium flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> Erros recentes
          </Label>
          {Array.isArray(recentErrors) && recentErrors.length > 0 ? (
            <ul className="space-y-1.5 text-sm">
              {recentErrors.slice(-5).map((err, idx) => (
                <li
                  key={`${err?.at || 'e'}-${idx}`}
                  className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-2 text-muted-foreground"
                >
                  <span className="text-xs shrink-0">{formatDateTime(err?.at)}</span>
                  <span className="text-foreground break-words">{err?.message || 'Erro técnico'}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Nenhum erro recente registrado.</p>
          )}
        </div>

        <Button variant="outline" onClick={onRefreshStatus} className="w-full">
          <RefreshCw className="h-4 w-4 mr-2" /> Atualizar status
        </Button>
      </CardContent>
    </Card>
  );
}

export default WhatsAppTab;
