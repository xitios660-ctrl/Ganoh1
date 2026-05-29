import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { CheckCircle2, Clock, ChefHat, Home, RefreshCw, Loader2, CreditCard, Banknote, Smartphone, WifiOff, XCircle, AlertCircle } from 'lucide-react';
import { Toaster, toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LOGO_URL = "/assets/ganoh-logo.png";

const STATUS_CONFIG = {
  pending_payment: { label: 'Aguardando Aprovação PIX', description: 'Seu comprovante está sendo verificado', icon: AlertCircle, color: 'text-blue-600', bgColor: 'bg-blue-50', step: 0 },
  payment_rejected: { label: 'Pagamento Recusado', description: 'O comprovante não foi aprovado. Fale com o atendente.', icon: XCircle, color: 'text-red-600', bgColor: 'bg-red-50', step: 0 },
  received: { label: 'Pedido Recebido', description: 'Seu pedido está na fila', icon: Clock, color: 'text-gray-600', bgColor: 'bg-gray-100', step: 1 },
  preparing: { label: 'Preparando', description: 'Estamos preparando seu pedido', icon: ChefHat, color: 'text-amber-600', bgColor: 'bg-amber-50', step: 2 },
  ready: { label: 'Pronto!', description: 'Seu pedido está pronto para retirada', icon: CheckCircle2, color: 'text-brand-600', bgColor: 'bg-brand-50', step: 3 },
  pending_sync: { label: 'Aguardando Sincronização', description: 'Seu pedido será enviado quando a conexão voltar', icon: WifiOff, color: 'text-amber-600', bgColor: 'bg-amber-50', step: 0 }
};

// Apenas os passos para a barra de progresso
const PROGRESS_STEPS = [
  { step: 1, label: 'Recebido' },
  { step: 2, label: 'Preparando' },
  { step: 3, label: 'Pronto' }
];

const PAYMENT_LABELS = { pix: 'PIX', debit: 'Cartão de Débito', credit: 'Cartão de Crédito', cash: 'Dinheiro' };
const PAYMENT_ICONS = { pix: Smartphone, debit: CreditCard, credit: CreditCard, cash: Banknote };

export const OrderTrackingPage = () => {
  const { store, orderId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isOfflineOrder, setIsOfflineOrder] = useState(false);

  const fetchOrder = async (showToast = false) => {
    // Handle offline orders
    if (orderId === 'offline') {
      setIsOfflineOrder(true);
      const customerName = searchParams.get('name') || 'Cliente';
      setOrder({
        id: 'offline',
        customer_name: customerName,
        status: 'pending_sync',
        items: [],
        total: 0
      });
      setIsLoading(false);
      return;
    }

    try {
      const response = await axios.get(`${API}/orders/${store}/${orderId}`);
      setOrder(response.data);
      if (showToast) toast.success('Status atualizado');
    } catch (error) {
      console.error('Erro:', error);
      toast.error('Erro ao carregar pedido');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchOrder();
    if (orderId !== 'offline') {
      const interval = setInterval(() => fetchOrder(), 10000);
      return () => clearInterval(interval);
    }
  }, [store, orderId]);

  const formatPrice = (price) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(price);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-10 h-10 text-brand-600 animate-spin" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="text-center">
          <p className="text-lg mb-4">Pedido não encontrado</p>
          <Button onClick={() => navigate(`/${store}`)} className="bg-brand-600 hover:bg-brand-700">
            <Home className="h-4 w-4 mr-2" /> Voltar
          </Button>
        </div>
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[order.status] || STATUS_CONFIG.received;
  const StatusIcon = statusConfig.icon;
  const PaymentIcon = PAYMENT_ICONS[order.payment_method] || Banknote;

  return (
    <div className={`min-h-screen ${statusConfig.bgColor} transition-colors`} data-testid="order-tracking-page">
      <Toaster position="top-center" richColors />
      
      <header className="bg-white/80 backdrop-blur-md border-b">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
          <img src={LOGO_URL} alt="GANOH" className="h-8" />
          {!isOfflineOrder && (
            <Button variant="outline" size="sm" onClick={() => { setIsRefreshing(true); fetchOrder(true); }} disabled={isRefreshing}>
              <RefreshCw className={`h-4 w-4 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          )}
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6">
        {/* Status Card */}
        <div className="bg-white rounded-2xl shadow-lg p-5 mb-4">
          <div className="text-center mb-5">
            <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full ${statusConfig.bgColor} mb-3`}>
              <StatusIcon className={`h-8 w-8 ${statusConfig.color}`} />
            </div>
            <h1 className={`text-xl font-bold ${statusConfig.color}`}>{statusConfig.label}</h1>
            <p className="text-sm text-muted-foreground">{statusConfig.description}</p>
          </div>

          {/* Progress - Só mostra se não for PIX pendente/rejeitado */}
          {order.status !== 'pending_payment' && order.status !== 'payment_rejected' && order.status !== 'pending_sync' && (
            <div className="flex items-center justify-center gap-2 mb-5">
              {PROGRESS_STEPS.map((item, index) => (
                <React.Fragment key={item.step}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    item.step <= statusConfig.step ? 'bg-brand-600 text-white' : 'bg-gray-200'
                  }`}>
                    {item.step}
                  </div>
                  {index < PROGRESS_STEPS.length - 1 && (
                    <div className={`h-1 w-8 ${item.step < statusConfig.step ? 'bg-brand-600' : 'bg-gray-200'}`} />
                  )}
                </React.Fragment>
              ))}
            </div>
          )}

          {/* Info */}
          <div className="bg-secondary/50 rounded-xl p-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Nome</span>
              <span className="font-medium">{order.customer_name}</span>
            </div>
            {order.pickup_time && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Retirada</span>
                <span className="font-medium text-brand-600">{order.pickup_time}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Pagamento</span>
              <span className="font-medium flex items-center gap-1">
                <PaymentIcon className="h-4 w-4" />
                {PAYMENT_LABELS[order.payment_method]}
              </span>
            </div>
          </div>
        </div>

        {/* Items */}
        {!isOfflineOrder && (
          <div className="bg-white rounded-2xl shadow-lg p-5">
            <h2 className="font-semibold mb-3">Itens do Pedido</h2>
            <div className="space-y-2 mb-3 text-sm">
              {order.items.map((item, idx) => (
                <div key={idx} className="flex justify-between py-1 border-b border-border/50 last:border-0">
                  <div>
                    <span className="font-medium">{item.name}</span>
                    <span className="text-muted-foreground ml-1">x{item.quantity}</span>
                  </div>
                  <span>{formatPrice(item.price * item.quantity)}</span>
                </div>
              ))}
            </div>
            <div className="border-t pt-3 flex justify-between">
              <span className="font-semibold">Total</span>
              <span className="text-xl font-bold text-brand-600">{formatPrice(order.total)}</span>
            </div>
          </div>
        )}

        {isOfflineOrder && (
          <div className="bg-white rounded-2xl shadow-lg p-5">
            <div className="text-center text-muted-foreground">
              <WifiOff className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p className="text-sm">Seu pedido foi salvo localmente.</p>
              <p className="text-sm">Quando a conexão for restaurada, ele será enviado automaticamente.</p>
            </div>
          </div>
        )}

        <div className="mt-4 text-center">
          <Button variant="outline" onClick={() => navigate(`/${store}`)} className="rounded-full">
            <Home className="h-4 w-4 mr-2" /> Novo Pedido
          </Button>
        </div>
      </main>
    </div>
  );
};
