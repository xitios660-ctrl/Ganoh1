import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../components/ui/select';
import { RadioGroup, RadioGroupItem } from '../components/ui/radio-group';
import { Switch } from '../components/ui/switch';
import { useCart } from '../context/CartContext';
import { useTheme } from '../context/ThemeContext';
import { User, ShoppingBag, Clock, CreditCard, Banknote, Smartphone, Receipt, Upload, Camera, Copy, CheckCircle2, QrCode, CalendarClock, WifiOff, Check, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { createOrder, isOnline, getOfflineOrders, syncOfflineOrders } from '../services/offlineService';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const PAYMENT_METHODS = [
  { id: 'pix', label: 'PIX', icon: Smartphone },
  { id: 'debit', label: 'Cartão de Débito', icon: CreditCard },
  { id: 'credit', label: 'Cartão de Crédito', icon: CreditCard },
  { id: 'cash', label: 'Dinheiro', icon: Banknote },
  { id: 'voucher', label: 'Voucher (VR/VA)', icon: CreditCard },
  { id: 'prazo', label: 'Prazo (Fiado)', icon: CalendarClock },
];

// PIX data - configured by store owner
const PIX_DATA = {
  key: "49289019000199",
  keyType: "CNPJ",
  beneficiaryName: "GANOH Café Bistrô",
  city: "São Paulo"
};

export const CheckoutModal = ({ isOpen, onClose, onSubmit, isLoading, store = 'runner' }) => {
  const [customerName, setCustomerName] = useState('');
  const [wantsSchedule, setWantsSchedule] = useState(false);
  const [pickupTime, setPickupTime] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('');
  const [pixProof, setPixProof] = useState(null);
  const [pixProofPreview, setPixProofPreview] = useState(null);
  const [step, setStep] = useState(1); // 1: info, 2: pix payment
  const [copied, setCopied] = useState(false);
  const [prazoCustomers, setPrazoCustomers] = useState([]);
  const [selectedPrazoCustomer, setSelectedPrazoCustomer] = useState('');
  const [prazoSearchTerm, setPrazoSearchTerm] = useState(''); // Search for prazo customers
  const [scheduleToggleCount, setScheduleToggleCount] = useState(0);
  const [showPrazo, setShowPrazo] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [offlineCount, setOfflineCount] = useState(0);
  const fileInputRef = useRef(null);
  const { items, total, itemCount, finalTotal, customTotal } = useCart();

  // Track online/offline status
  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      // Try to sync offline orders when back online
      syncOfflineOrders().then(result => {
        if (result.synced > 0) {
          toast.success(`${result.synced} pedido(s) sincronizado(s)!`);
        }
      }).catch(console.error);
    };
    const handleOffline = () => setOnline(false);
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    // Check for pending offline orders
    const pending = getOfflineOrders().filter(o => !o.synced);
    setOfflineCount(pending.length);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Fetch prazo customers only when user searches (privacy fix)
  useEffect(() => {
    if (!isOpen || paymentMethod !== 'prazo') {
      setPrazoCustomers([]);
      return;
    }
    const q = (prazoSearchTerm || '').trim();
    if (q.length < 2) {
      setPrazoCustomers([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      axios.get(`${API}/prazo/customers/lookup`, { params: { q, store }, signal: ctrl.signal })
        .then(res => setPrazoCustomers(res.data.customers || []))
        .catch(() => {});
    }, 250);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [isOpen, paymentMethod, prazoSearchTerm, store]);

  // Reset modal state when opened
  useEffect(() => {
    if (isOpen) {
      setScheduleToggleCount(0);
      setShowPrazo(false);
    }
  }, [isOpen]);

  // Handle schedule toggle - unlock prazo after 5 toggles
  const handleScheduleToggle = (checked) => {
    setWantsSchedule(checked);
    const newCount = scheduleToggleCount + 1;
    setScheduleToggleCount(newCount);
    
    if (newCount >= 5 && !showPrazo) {
      setShowPrazo(true);
      toast.success('🔓 Opção Prazo desbloqueada!', { duration: 2000 });
    }
  };

  // Get available payment methods - prazo only shows after 5 toggles
  const availablePaymentMethods = showPrazo 
    ? PAYMENT_METHODS 
    : PAYMENT_METHODS.filter(m => m.id !== 'prazo');

  // Generate time slots respecting business hours (08:00 - 22:00) for both stores
  // Skips slots in the past and slots before opening time.
  const timeSlots = useMemo(() => {
    const OPENING_HOUR = 8;   // 08:00
    const CLOSING_HOUR = 22;  // 22:00 (last slot)
    const STEP_MIN = 15;
    const slots = [];

    const now = new Date();
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes();

    // Start at least 15 minutes from now, rounded to next 15-min slot
    let startHour = currentHour;
    let startMinute = Math.ceil((currentMinute + STEP_MIN) / STEP_MIN) * STEP_MIN;
    if (startMinute >= 60) {
      startMinute -= 60;
      startHour += 1;
    }

    // Clamp to opening time
    if (startHour < OPENING_HOUR) {
      startHour = OPENING_HOUR;
      startMinute = 0;
    }

    // If already past closing, no slots today
    if (startHour > CLOSING_HOUR || (startHour === CLOSING_HOUR && startMinute > 0)) {
      return [];
    }

    for (let hour = startHour; hour <= CLOSING_HOUR; hour++) {
      const minuteStart = hour === startHour ? startMinute : 0;
      for (let minute = minuteStart; minute < 60; minute += STEP_MIN) {
        if (hour === CLOSING_HOUR && minute > 0) break;
        const timeStr = `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
        slots.push(timeStr);
      }
    }

    return slots;
  }, []);

  // Group time slots by period of day (Manhã / Tarde / Noite) for better UX.
  // Used in the select dropdown.
  const timeSlotGroups = useMemo(() => {
    const groups = { 'Manhã': [], 'Tarde': [], 'Noite': [] };
    for (const t of timeSlots) {
      const h = parseInt(t.slice(0, 2), 10);
      if (h < 12) groups['Manhã'].push(t);
      else if (h < 18) groups['Tarde'].push(t);
      else groups['Noite'].push(t);
    }
    return groups;
  }, [timeSlots]);

  const formatPrice = (price) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(price);
  };

  // PIX copy-paste - just the CNPJ key
  const getPixKey = () => PIX_DATA.key;

  const handleCopyPix = () => {
    navigator.clipboard.writeText(PIX_DATA.key);
    setCopied(true);
    toast.success('CNPJ copiado!');
    setTimeout(() => setCopied(false), 3000);
  };

  // Compress image for faster upload
  const compressImage = (file, maxWidth = 800, quality = 0.6) => {
    return new Promise((resolve) => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const img = new Image();
      
      img.onload = () => {
        let width = img.width;
        let height = img.height;
        
        if (width > maxWidth) {
          height = (height * maxWidth) / width;
          width = maxWidth;
        }
        
        canvas.width = width;
        canvas.height = height;
        ctx.drawImage(img, 0, 0, width, height);
        
        resolve(canvas.toDataURL('image/jpeg', quality));
      };
      
      img.src = URL.createObjectURL(file);
    });
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 10 * 1024 * 1024) {
        toast.error('Imagem muito grande. Máximo 10MB.');
        return;
      }
      
      toast.loading('Processando imagem...', { id: 'compress' });
      
      try {
        // Compress the image
        const compressedImage = await compressImage(file);
        setPixProof(compressedImage);
        setPixProofPreview(compressedImage);
        toast.success('Comprovante carregado!', { id: 'compress' });
      } catch (error) {
        toast.error('Erro ao processar imagem', { id: 'compress' });
      }
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (paymentMethod === 'pix') {
      if (step === 1) {
        setStep(2);
        return;
      }
      
      if (!pixProof) {
        toast.error('Por favor, envie o comprovante de pagamento');
        return;
      }
    }
    
    if (customerName.trim() && paymentMethod) {
      const finalPickupTime = wantsSchedule && pickupTime ? pickupTime : null;
      onSubmit(customerName.trim(), finalPickupTime, paymentMethod, pixProof, finalTotal);
    }
  };

  const handleClose = () => {
    setCustomerName('');
    setWantsSchedule(false);
    setPickupTime('');
    setPaymentMethod('');
    setPixProof(null);
    setPixProofPreview(null);
    setStep(1);
    setCopied(false);
    onClose();
  };

  const handleBack = () => {
    if (step === 2) {
      setStep(1);
    } else {
      handleClose();
    }
  };

  const canSubmitStep1 = customerName.trim() && paymentMethod && (!wantsSchedule || pickupTime);
  const canSubmitStep2 = pixProof !== null;

  const { theme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className={`sm:max-w-md max-h-[90vh] overflow-y-auto border-0 ${isDark ? 'bg-[#0a0a0a] text-white' : 'bg-white'}`}>
        <DialogHeader>
          <DialogTitle className={`font-heading text-2xl flex items-center gap-2 ${isDark ? 'text-white' : ''}`}>
            {step === 1 ? (
              <>
                <ShoppingBag className="h-6 w-6 text-brand-600" />
                Finalizar Pedido
              </>
            ) : (
              <>
                <Smartphone className="h-6 w-6 text-brand-600" />
                Pagamento PIX
              </>
            )}
          </DialogTitle>
          {/* Offline indicator */}
          {!online && (
            <div className={`flex items-center gap-2 text-sm mt-1 ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
              <WifiOff className="h-4 w-4" />
              Modo offline - Pedido será enviado quando voltar a internet
            </div>
          )}
          {offlineCount > 0 && online && (
            <div className={`text-xs mt-1 ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>
              {offlineCount} pedido(s) pendente(s) para sincronizar
            </div>
          )}
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          {step === 1 ? (
            <>
              {/* Order Summary */}
              <div className={`rounded-xl p-4 space-y-2 ${isDark ? 'bg-white/[0.05] border border-white/10' : 'bg-secondary/50'}`}>
                <div className="flex justify-between text-sm">
                  <span className={isDark ? 'text-white/60' : 'text-muted-foreground'}>Itens</span>
                  <span className={`font-medium ${isDark ? 'text-white' : ''}`}>{itemCount}</span>
                </div>
                <div className="flex justify-between">
                  <span className={isDark ? 'text-white/60' : 'text-muted-foreground'}>Total</span>
                  <span className={`text-xl font-bold ${customTotal !== null && customTotal !== total ? (isDark ? 'text-amber-400' : 'text-amber-600') : (isDark ? 'text-[#a8d96b]' : 'text-brand-600')}`}>
                    {formatPrice(finalTotal)}
                  </span>
                </div>
                {customTotal !== null && customTotal !== total && (
                  <p className={`text-xs text-right ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                    Valor original: {formatPrice(total)} | Desconto: {formatPrice(total - customTotal)}
                  </p>
                )}
              </div>

              {/* Customer Name */}
              <div className="space-y-2">
                <Label htmlFor="customer-name" className={`text-sm font-medium flex items-center gap-2 ${isDark ? 'text-white/80' : ''}`}>
                  <User className={`h-4 w-4 ${isDark ? 'text-white/50' : 'text-muted-foreground'}`} />
                  Seu Nome
                </Label>
                <Input
                  id="customer-name"
                  placeholder="Digite seu nome"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className={`h-11 ${isDark ? 'bg-white/[0.04] border-white/15 text-white placeholder:text-white/40 focus-visible:border-[#a8d96b]/50 focus-visible:ring-[#a8d96b]/20' : ''}`}
                  required
                  data-testid="customer-name-input"
                />
              </div>

              {/* Schedule Toggle */}
              <div className={`flex items-center justify-between p-3 rounded-lg ${isDark ? 'bg-white/[0.04] border border-white/10' : 'bg-secondary/30'}`}>
                <div className="flex items-center gap-2">
                  <Clock className={`h-4 w-4 ${isDark ? 'text-white/60' : 'text-muted-foreground'}`} />
                  <Label htmlFor="schedule-toggle" className={`text-sm font-medium cursor-pointer ${isDark ? 'text-white/90' : ''}`}>
                    Agendar horário de retirada
                  </Label>
                </div>
                <Switch
                  id="schedule-toggle"
                  checked={wantsSchedule}
                  onCheckedChange={handleScheduleToggle}
                  data-testid="schedule-toggle"
                />
              </div>

              {/* Pickup Time (conditional) */}
              {wantsSchedule && (
                <div className="space-y-2 animate-slideIn">
                  <Label htmlFor="pickup-time" className={`text-sm font-medium ${isDark ? 'text-white/80' : ''}`}>
                    Horário para Retirada
                  </Label>
                  <Select value={pickupTime} onValueChange={setPickupTime}>
                    <SelectTrigger className={`h-11 ${isDark ? 'bg-white/[0.04] border-white/15 text-white' : ''}`} data-testid="pickup-time-select">
                      <SelectValue placeholder="Selecione o horário" />
                    </SelectTrigger>
                    <SelectContent className={isDark ? 'bg-[#161616] border-white/15 text-white' : ''}>
                      {timeSlots.length === 0 ? (
                        <SelectItem value="closed" disabled>Fechado</SelectItem>
                      ) : (
                        Object.entries(timeSlotGroups).map(([groupLabel, slots]) => (
                          slots.length > 0 ? (
                            <SelectGroup key={groupLabel}>
                              <SelectLabel className={isDark ? 'text-white/50' : 'text-muted-foreground'}>
                                {groupLabel}
                              </SelectLabel>
                              {slots.map((time) => (
                                <SelectItem key={time} value={time}>{time}</SelectItem>
                              ))}
                            </SelectGroup>
                          ) : null
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Payment Method */}
              <div className="space-y-3">
                <Label className={`text-sm font-medium flex items-center gap-2 ${isDark ? 'text-white/80' : ''}`}>
                  <Receipt className={`h-4 w-4 ${isDark ? 'text-white/50' : 'text-muted-foreground'}`} />
                  Forma de Pagamento
                </Label>
                <RadioGroup value={paymentMethod} onValueChange={(v) => { setPaymentMethod(v); if (v !== 'prazo') setSelectedPrazoCustomer(''); }} className="grid grid-cols-2 gap-2">
                  {availablePaymentMethods.filter(m => m.id !== 'prazo').map((method) => {
                    const Icon = method.icon;
                    const selected = paymentMethod === method.id;
                    return (
                      <label
                        key={method.id}
                        className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer transition-all ${
                          selected
                            ? (isDark
                                ? 'border-[#a8d96b] bg-[#a8d96b]/15'
                                : 'border-brand-500 bg-brand-50')
                            : (isDark
                                ? 'border-white/15 bg-white/[0.03] hover:border-[#a8d96b]/50 hover:bg-white/[0.06]'
                                : 'border-border hover:border-brand-200')
                        }`}
                        data-testid={`payment-${method.id}`}
                      >
                        <RadioGroupItem value={method.id} className="sr-only" />
                        <Icon className={`h-4 w-4 ${
                          selected
                            ? (isDark ? 'text-[#a8d96b]' : 'text-brand-600')
                            : (isDark ? 'text-white/60' : 'text-muted-foreground')
                        }`} />
                        <span className={`text-sm font-medium ${
                          selected
                            ? (isDark ? 'text-[#a8d96b]' : 'text-brand-700')
                            : (isDark ? 'text-white/90' : 'text-foreground')
                        }`}>
                          {method.label}
                        </span>
                      </label>
                    );
                  })}
                </RadioGroup>

                {/* Prazo - Destacado separadamente */}
                <div
                  onClick={() => { setPaymentMethod('prazo'); setSelectedPrazoCustomer(''); }}
                  className={`flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all ${
                    paymentMethod === 'prazo'
                      ? (isDark
                          ? 'border-amber-400 bg-amber-400/15'
                          : 'border-amber-500 bg-amber-50')
                      : (isDark
                          ? 'border-amber-400/40 bg-amber-400/[0.06] hover:border-amber-400/70'
                          : 'border-amber-200 bg-amber-50/30 hover:border-amber-400')
                  }`}
                  data-testid="payment-prazo"
                >
                  <CalendarClock className={`h-5 w-5 ${
                    paymentMethod === 'prazo'
                      ? (isDark ? 'text-amber-300' : 'text-amber-600')
                      : (isDark ? 'text-amber-400' : 'text-amber-500')
                  }`} />
                  <div className="flex-1">
                    <span className={`text-sm font-bold ${
                      paymentMethod === 'prazo'
                        ? (isDark ? 'text-amber-200' : 'text-amber-700')
                        : (isDark ? 'text-amber-300' : 'text-amber-600')
                    }`}>
                      Prazo (Fiado)
                    </span>
                    <p className={`text-xs ${isDark ? 'text-amber-300/80' : 'text-amber-600/70'}`}>Pagar depois</p>
                  </div>
                  {paymentMethod === 'prazo' && (
                    <Check className={`h-5 w-5 ${isDark ? 'text-amber-300' : 'text-amber-600'}`} />
                  )}
                </div>
              </div>

              {paymentMethod === 'pix' && (
                <div className={`rounded-lg p-3 text-sm ${
                  isDark
                    ? 'bg-blue-400/10 border border-blue-400/30 text-blue-200'
                    : 'bg-blue-50 border border-blue-200 text-blue-700'
                }`}>
                  <p className="font-medium">ℹ️ Pagamento via PIX</p>
                  <p className="text-xs mt-1 opacity-90">Na próxima etapa você verá o QR Code e poderá enviar o comprovante.</p>
                </div>
              )}

              {paymentMethod === 'prazo' && (
                <div className="space-y-3">
                  <div className={`rounded-lg p-3 text-sm ${
                    isDark
                      ? 'bg-amber-400/10 border border-amber-400/30 text-amber-200'
                      : 'bg-amber-50 border border-amber-200 text-amber-700'
                  }`}>
                    <p className="font-medium">⚠️ Pagamento a Prazo</p>
                    <p className="text-xs mt-1 opacity-90">O valor será registrado para pagamento posterior.</p>
                  </div>

                  <div className="space-y-2">
                    <Label className={`text-sm ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>
                      Buscar cliente cadastrado (opcional, mínimo 2 letras)
                    </Label>

                    {/* Search input for prazo customers - server-side, name-only */}
                    <div className="relative">
                      <Search className={`absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 ${isDark ? 'text-white/40' : 'text-muted-foreground'}`} />
                      <Input
                        type="text"
                        placeholder="Digite o nome do cliente..."
                        value={prazoSearchTerm}
                        onChange={(e) => setPrazoSearchTerm(e.target.value)}
                        className={`pl-10 h-10 ${isDark ? 'bg-white/[0.04] border-white/15 text-white placeholder:text-white/40' : ''}`}
                        data-testid="prazo-search-input"
                      />
                      {prazoSearchTerm && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label="Limpar busca"
                          className={`absolute right-1 top-1/2 transform -translate-y-1/2 h-8 w-8 ${isDark ? 'text-white/60 hover:text-white hover:bg-white/10' : ''}`}
                          onClick={() => setPrazoSearchTerm('')}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                    </div>

                    {/* Result list - only shows when 2+ chars typed */}
                    {prazoSearchTerm.trim().length >= 2 && (
                      <div className={`max-h-48 overflow-y-auto rounded-lg ${isDark ? 'bg-white/[0.03] border border-white/10' : 'bg-black/[0.02]'}`}>
                        {prazoCustomers.map((c) => (
                          <button
                            key={c.id}
                            type="button"
                            className={`w-full text-left px-3 py-2 transition-colors ${
                              isDark ? 'text-white/90 hover:bg-white/[0.05]' : 'hover:bg-black/[0.04]'
                            } ${
                              selectedPrazoCustomer === c.name ? (isDark ? 'bg-amber-400/15 text-amber-200 font-medium' : 'bg-amber-50 text-amber-700 font-medium') : ''
                            }`}
                            onClick={() => {
                              setSelectedPrazoCustomer(c.name);
                              setCustomerName(c.name);
                              setPrazoSearchTerm('');
                            }}
                            data-testid={`prazo-customer-${c.id}`}
                          >
                            {c.name}
                            {c.phone_masked && (
                              <span className={`text-xs ml-2 ${isDark ? 'text-white/40' : 'text-muted-foreground'}`}>
                                ({c.phone_masked})
                              </span>
                            )}
                          </button>
                        ))}
                        {prazoCustomers.length === 0 && (
                          <p className={`px-3 py-2 text-sm ${isDark ? 'text-white/50' : 'text-muted-foreground'}`}>
                            Nenhum cliente encontrado
                          </p>
                        )}
                      </div>
                    )}

                    {selectedPrazoCustomer && (
                      <p className={`text-xs ${isDark ? 'text-amber-300' : 'text-amber-600'}`}>
                        Selecionado: <strong>{selectedPrazoCustomer}</strong>
                        <button
                          type="button"
                          className={`ml-2 hover:underline ${isDark ? 'text-red-400' : 'text-red-500'}`}
                          onClick={() => { setSelectedPrazoCustomer(''); setCustomerName(''); }}
                        >
                          (limpar)
                        </button>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {/* PIX Payment Step */}
              <div className="space-y-4">
                {/* Amount */}
                <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-[#a8d96b]/10 border border-[#a8d96b]/30' : 'bg-brand-50'}`}>
                  <p className={`text-sm mb-1 ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>Valor a pagar</p>
                  <p className={`text-3xl font-bold ${customTotal !== null && customTotal !== total ? (isDark ? 'text-amber-300' : 'text-amber-600') : (isDark ? 'text-[#a8d96b]' : 'text-brand-600')}`}>{formatPrice(finalTotal)}</p>
                  <p className={`text-xs mt-1 ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>{customerName}</p>
                  {customTotal !== null && customTotal !== total && (
                    <p className={`text-xs mt-1 ${isDark ? 'text-amber-300' : 'text-amber-600'}`}>Valor com desconto</p>
                  )}
                </div>

                {/* QR Code do PIX */}
                <div className={`rounded-xl p-4 text-center ${isDark ? 'bg-white/[0.04]' : 'bg-white shadow-sm'}`}>
                  <img 
                    src="/images/pix-qrcode.png" 
                    alt="QR Code PIX" 
                    className="h-48 w-48 mx-auto mb-3"
                  />
                  <p className={`text-xs ${isDark ? 'text-white/50' : 'text-muted-foreground'}`}>
                    Escaneie o QR Code acima ou use o código abaixo
                  </p>
                </div>

                {/* PIX Copy-Paste - CNPJ */}
                <div className="space-y-2">
                  <Label className={`text-sm font-medium ${isDark ? 'text-white/80' : ''}`}>Chave PIX (CNPJ)</Label>
                  <div className="flex gap-2">
                    <Input
                      value={PIX_DATA.key}
                      readOnly
                      className={`text-base font-mono font-bold tracking-wider ${isDark ? 'bg-white/[0.04] border-white/15 text-white' : ''}`}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={handleCopyPix}
                      className={
                        copied
                          ? (isDark ? 'bg-green-500/15 border-green-400/50 text-green-300' : 'bg-green-50 border-green-500')
                          : (isDark ? 'bg-white/[0.04] border-white/15 text-white hover:bg-white/[0.08]' : '')
                      }
                    >
                      {copied ? (
                        <CheckCircle2 className={`h-4 w-4 ${isDark ? 'text-green-300' : 'text-green-600'}`} />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>

                {/* Upload Proof */}
                <div className="space-y-2">
                  <Label className={`text-sm font-medium flex items-center gap-2 ${isDark ? 'text-white/80' : ''}`}>
                    <Upload className={`h-4 w-4 ${isDark ? 'text-white/50' : 'text-muted-foreground'}`} />
                    Enviar Comprovante *
                  </Label>

                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    accept="image/*"
                    className="hidden"
                    data-testid="pix-proof-input"
                  />

                  {pixProofPreview ? (
                    <div className="relative">
                      <img
                        src={pixProofPreview}
                        alt="Comprovante"
                        className={`w-full h-40 object-cover rounded-lg border ${isDark ? 'border-white/15' : ''}`}
                      />
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        className="absolute bottom-2 right-2"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Camera className="h-4 w-4 mr-1" />
                        Trocar
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      className={`w-full h-24 border-dashed flex flex-col gap-2 ${
                        isDark ? 'bg-white/[0.03] border-white/20 text-white/80 hover:bg-white/[0.06] hover:border-[#a8d96b]/40' : ''
                      }`}
                      onClick={() => fileInputRef.current?.click()}
                      data-testid="upload-proof-button"
                    >
                      <Camera className={`h-6 w-6 ${isDark ? 'text-white/60' : 'text-muted-foreground'}`} />
                      <span className="text-sm">Tirar foto ou selecionar imagem</span>
                    </Button>
                  )}

                  <p className={`text-xs ${isDark ? 'text-white/50' : 'text-muted-foreground'}`}>
                    Envie uma foto ou screenshot do comprovante de pagamento
                  </p>
                </div>
              </div>
            </>
          )}

          <DialogFooter className="flex-col sm:flex-col gap-2 pt-2">
            <Button
              type="submit"
              className={`w-full h-12 text-base font-semibold transition-all ${
                isDark
                  ? 'bg-[#a8d96b] hover:bg-[#bce283] text-black shadow-[0_8px_24px_-8px_rgba(168,217,107,0.6)]'
                  : 'bg-brand-600 hover:bg-brand-700 text-white'
              }`}
              disabled={step === 1 ? (!canSubmitStep1 || isLoading) : (!canSubmitStep2 || isLoading)}
              data-testid="confirm-order-button"
            >
              {isLoading ? 'Enviando...' : (
                step === 1 ? (paymentMethod === 'pix' ? 'Continuar para PIX' : 'Confirmar Pedido') : 'Enviar Pedido'
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              className={`w-full ${
                isDark
                  ? 'bg-transparent border-white/20 text-white/90 hover:bg-white/[0.06] hover:border-white/40'
                  : ''
              }`}
              onClick={handleBack}
            >
              Voltar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
