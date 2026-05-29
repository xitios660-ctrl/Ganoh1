import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { MessageCircle, Users, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

export function WhatsAppTab({ 
  whatsappStatus, 
  whatsappQR, 
  whatsappGroups,
  whatsappTarget,
  whatsappTargetInput,
  setWhatsappTargetInput,
  onJoinGroup,
  onRefreshStatus
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageCircle className="h-5 w-5 text-green-600" />
          WhatsApp Bot - Notificações PIX
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-sm text-muted-foreground mb-4">
          Conecte o WhatsApp para receber notificações automáticas quando um PIX for aprovado.
        </div>
        
        {/* Status */}
        <div className="flex items-center gap-3 p-4 bg-secondary/30 rounded-lg">
          <div className={`w-3 h-3 rounded-full ${
            whatsappStatus === 'connected' ? 'bg-green-500' :
            whatsappStatus === 'waiting_qr' ? 'bg-yellow-500 animate-pulse' :
            whatsappStatus === 'reconnecting' ? 'bg-blue-500 animate-pulse' :
            'bg-red-500'
          }`} />
          <span className="font-medium">
            {whatsappStatus === 'connected' ? '✅ Conectado' :
             whatsappStatus === 'waiting_qr' ? '📱 Aguardando QR Code...' :
             whatsappStatus === 'reconnecting' ? '🔄 Reconectando...' :
             whatsappStatus === 'offline' ? '⚠️ Bot offline (inicie o serviço)' :
             '❌ Desconectado'}
          </span>
        </div>

        {/* QR Code */}
        {whatsappQR && whatsappStatus !== 'connected' && (
          <div className="bg-white p-6 rounded-lg border text-center">
            <p className="text-sm font-medium mb-4">Escaneie o QR Code com seu WhatsApp:</p>
            <div className="inline-block p-4 bg-white border rounded-lg">
              <img 
                src={`data:image/png;base64,${whatsappQR}`}
                alt="WhatsApp QR Code"
                className="w-48 h-48"
              />
            </div>
            <p className="text-xs text-muted-foreground mt-4">
              1. Abra o WhatsApp no celular<br/>
              2. Vá em Configurações → Aparelhos Conectados<br/>
              3. Escaneie o código acima
            </p>
          </div>
        )}

        {/* Show "Get QR Code" button when not connected and no QR */}
        {!whatsappQR && whatsappStatus !== 'connected' && whatsappStatus !== 'offline' && (
          <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200 text-center">
            <p className="text-yellow-700 font-medium mb-3">📱 WhatsApp não conectado</p>
            <p className="text-sm text-yellow-600 mb-4">
              Clique no botão abaixo para gerar o QR Code e reconectar.
            </p>
            <Button 
              onClick={onRefreshStatus}
              className="bg-green-600 hover:bg-green-700"
            >
              <RefreshCw className="h-4 w-4 mr-2" /> Gerar QR Code
            </Button>
          </div>
        )}

        {whatsappStatus === 'connected' && (
          <div className="space-y-4">
            <div className="bg-green-50 p-4 rounded-lg border border-green-200">
              <p className="text-green-700 font-medium">🎉 WhatsApp conectado com sucesso!</p>
              <p className="text-sm text-green-600 mt-2">
                Quando um PIX for aprovado, você receberá uma notificação automática com a foto do comprovante.
              </p>
            </div>
            
            {/* Configurar destino das notificações */}
            <div className="bg-secondary/30 p-4 rounded-lg border">
              <Label className="font-medium flex items-center gap-2 mb-2">
                <Users className="h-4 w-4" /> Destino das Notificações
              </Label>
              <p className="text-xs text-muted-foreground mb-3">
                Cole o link do grupo WhatsApp para entrar e receber notificações
              </p>
              <div className="flex gap-2">
                <Input 
                  value={whatsappTargetInput}
                  onChange={(e) => setWhatsappTargetInput(e.target.value)}
                  placeholder="https://chat.whatsapp.com/xxx"
                  className="flex-1"
                />
                <Button onClick={onJoinGroup} className="bg-green-600 hover:bg-green-700">
                  Entrar no Grupo
                </Button>
              </div>
              {whatsappTarget && (
                <p className="text-xs text-muted-foreground mt-2">
                  ✅ Destino atual: <code className="bg-secondary px-1 rounded">{whatsappTarget}</code>
                </p>
              )}
            </div>
            
            {/* Grupos disponíveis */}
            {whatsappGroups.length > 0 && (
              <div className="bg-secondary/30 p-4 rounded-lg border">
                <Label className="font-medium flex items-center gap-2 mb-2">
                  <MessageCircle className="h-4 w-4" /> Grupos Disponíveis
                </Label>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {whatsappGroups.map((group) => (
                    <div 
                      key={group.id} 
                      className="flex items-center justify-between p-2 bg-white rounded border text-sm hover:bg-secondary/50 cursor-pointer"
                      onClick={() => {
                        setWhatsappTargetInput(group.id);
                        toast.info(`Grupo "${group.name}" selecionado. Clique em Salvar.`);
                      }}
                    >
                      <span>{group.name}</span>
                      <span className="text-xs text-muted-foreground">{group.participants} membros</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {whatsappStatus === 'offline' && (
          <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
            <p className="text-yellow-700 font-medium">⚠️ Serviço do bot não está rodando</p>
            <p className="text-sm text-yellow-600 mt-2">
              O bot do WhatsApp precisa ser iniciado no servidor.
            </p>
          </div>
        )}

        <Button 
          variant="outline" 
          onClick={onRefreshStatus}
          className="w-full"
        >
          <RefreshCw className="h-4 w-4 mr-2" /> Atualizar Status
        </Button>
      </CardContent>
    </Card>
  );
}

export default WhatsAppTab;
