import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { ScrollArea } from '../components/ui/scroll-area';
import { 
  Clock, ChefHat, CheckCircle2, RefreshCw, Trash2, Package, 
  Home, Smartphone, Plus, Minus, Banknote, CreditCard,
  AlertTriangle, Coffee, Droplets, Image, X, Check, History, Sun, Moon, Volume2, VolumeX, CalendarClock, MessageCircle, Loader2, Pencil, UtensilsCrossed, UserPlus, DollarSign, Ticket, RotateCcw, Search, MapPin, ArrowLeftRight
} from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Toaster, toast } from 'sonner';
import { useKitchenBell } from '../hooks/useKitchenBell';
import { ThemeToggle } from '../components/ThemeToggle';
import { useTheme } from '../context/ThemeContext';
import { Bell, BellOff } from 'lucide-react';
import { KitchenStage3D } from '../components/KitchenStage3D';
import '../styles/kitchen-cinematic.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STORE_NAMES = { 'runner': 'Runner', 'gym-londres': 'GYM Londres' };

const STATUS_CONFIG = {
  pending_payment: { label: 'Aguardando PIX', color: 'bg-blue-500', bgLight: 'bg-blue-50', borderColor: 'border-l-blue-500' },
  received: { label: 'Recebido', color: 'bg-gray-500', bgLight: 'bg-gray-50', borderColor: 'border-l-gray-500' },
  preparing: { label: 'Preparando', color: 'bg-amber-500', bgLight: 'bg-amber-50', borderColor: 'border-l-amber-500' },
  ready: { label: 'Pronto', color: 'bg-brand-500', bgLight: 'bg-brand-50', borderColor: 'border-l-brand-500' }
};

const PAYMENT_ICONS = { pix: Smartphone, debit: CreditCard, credit: CreditCard, cash: Banknote, prazo: Clock, voucher: Ticket };
const PAYMENT_LABELS = { pix: 'PIX', debit: 'Débito', credit: 'Crédito', cash: 'Dinheiro', prazo: 'Prazo', voucher: 'Voucher' };

const formatTime = (isoString) => {
  const date = new Date(isoString);
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

const formatCurrency = (value) => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(value);
};

// Order Card Component - Mobile optimized
const OrderCard = ({ order, onStatusChange, onDelete }) => {
  const config = STATUS_CONFIG[order.status] || STATUS_CONFIG.received;
  const createdAt = new Date(order.created_at);
  const now = new Date();
  const minutesAgo = Math.floor((now - createdAt) / 60000);
  const PaymentIcon = PAYMENT_ICONS[order.payment_method] || Banknote;

  const getNextStatus = () => {
    if (order.status === 'received') return 'preparing';
    if (order.status === 'preparing') return 'ready';
    return null;
  };

  return (
    <div className={`bg-white rounded-lg border-l-4 ${config.borderColor} shadow-sm`}>
      <div className={`px-2 py-1.5 ${config.bgLight} flex items-center justify-between`}>
        <span className="font-bold text-sm truncate flex-1">{order.customer_name}</span>
        <div className="flex items-center gap-1 text-xs text-muted-foreground ml-1">
          <PaymentIcon className="h-3 w-3" />
          {order.pickup_time && <span className="text-brand-600 font-medium">{order.pickup_time}</span>}
          <span>{minutesAgo}m</span>
        </div>
      </div>
      <div className="p-2">
        <div className="text-xs space-y-0.5 mb-2">
          {order.items.slice(0, 3).map((item, idx) => (
            <div key={`${order.id}-item-${idx}`} className="truncate"><b>{item.quantity}x</b> {item.name}</div>
          ))}
          {order.items.length > 3 && <div className="text-muted-foreground">+{order.items.length - 3} itens</div>}
        </div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-brand-600">{formatCurrency(order.total)}</span>
        </div>
        <div className="flex items-center justify-end gap-1">
          <div className="flex gap-1">
            {getNextStatus() === 'preparing' && (
              <Button size="sm" className="h-7 px-2 text-xs bg-amber-500 hover:bg-amber-600" onClick={() => onStatusChange(order.id, 'preparing')}>
                Preparar
              </Button>
            )}
            {getNextStatus() === 'ready' && (
              <Button size="sm" className="h-7 px-2 text-xs bg-brand-600 hover:bg-brand-700" onClick={() => onStatusChange(order.id, 'ready')}>
                Pronto
              </Button>
            )}
            {order.status === 'ready' && (
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs text-destructive" onClick={() => onDelete(order.id)}>
                <Trash2 className="h-3 w-3" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// PIX Pending Card Component
const PixPendingCard = ({ order, onApprove, onReject, onViewProof, onRetryVerify }) => {
  const createdAt = new Date(order.created_at);
  const proofUploadedAt = order.pix_proof_at ? new Date(order.pix_proof_at) : null;
  const now = new Date();
  const minutesAgo = Math.floor((now - createdAt) / 60000);
  
  // Calculate time since proof upload for verification status
  // If no pix_proof_at, consider it as already timed out (legacy order)
  const secondsSinceProofUpload = proofUploadedAt ? Math.floor((now - proofUploadedAt) / 1000) : 999;
  const isVerifying = order.pix_proof && !order.pix_analysis && secondsSinceProofUpload < 30;
  const verificationTimedOut = order.pix_proof && !order.pix_analysis && secondsSinceProofUpload >= 30;

  return (
    <div className="bg-white rounded-lg border-l-4 border-l-blue-500 shadow-sm">
      <div className="px-2 py-1.5 bg-blue-50 flex items-center justify-between">
        <span className="font-bold text-sm truncate flex-1">{order.customer_name}</span>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Smartphone className="h-3 w-3 text-blue-600" />
          <span>{minutesAgo}m</span>
        </div>
      </div>
      <div className="p-2">
        <div className="text-xs space-y-0.5 mb-2">
          {order.items.slice(0, 2).map((item, idx) => (
            <div key={`${order.id}-pix-item-${idx}`} className="truncate"><b>{item.quantity}x</b> {item.name}</div>
          ))}
          {order.items.length > 2 && <div className="text-muted-foreground">+{order.items.length - 2} itens</div>}
        </div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-blue-600">{formatCurrency(order.total)}</span>
          {order.pix_proof && (
            <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={() => onViewProof(order)}>
              <Image className="h-3 w-3 mr-1" />
              Ver
            </Button>
          )}
        </div>
        
        {/* AI Status indicator - Verifying */}
        {isVerifying && (
          <div className="w-full h-8 text-xs bg-purple-100 text-purple-700 rounded flex items-center justify-center gap-2 mb-2">
            <Loader2 className="h-3 w-3 animate-spin" />
            IA verificando... ({Math.max(0, 30 - secondsSinceProofUpload)}s)
          </div>
        )}
        
        {/* AI Status indicator - Timed out (needs manual check or retry) */}
        {verificationTimedOut && (
          <div className="w-full text-xs bg-amber-100 text-amber-700 rounded p-2 mb-2 flex items-center justify-between">
            <span>⏳ Verificar manualmente ou</span>
            <Button 
              size="sm" 
              variant="outline" 
              className="h-6 px-2 text-xs ml-2"
              onClick={() => onRetryVerify && onRetryVerify(order.id)}
            >
              🔄 Tentar IA
            </Button>
          </div>
        )}
        
        {/* AI Analysis result */}
        {order.pix_analysis && (
          <div className={`w-full text-xs rounded p-2 mb-2 ${order.pix_analysis.is_valid ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
            {order.pix_analysis.is_valid ? '✅ IA aprovou!' : `⚠️ ${order.pix_analysis.reason}`}
            {order.pix_payer_name && <div className="text-[10px] mt-1">Pagador: {order.pix_payer_name}</div>}
            {order.pix_transaction_time && <div className="text-[10px]">Horário: {order.pix_transaction_time}</div>}
          </div>
        )}
        
        <div className="flex gap-1">
          <Button 
            size="sm" 
            className="flex-1 h-7 text-xs bg-green-600 hover:bg-green-700" 
            onClick={() => onApprove(order.id)}
            disabled={!order.pix_proof}
          >
            <Check className="h-3 w-3 mr-1" />
            Aprovar
          </Button>
          <Button 
            size="sm" 
            variant="outline" 
            className="flex-1 h-7 text-xs text-red-600 border-red-200 hover:bg-red-50" 
            onClick={() => onReject(order.id)}
          >
            <X className="h-3 w-3 mr-1" />
            Recusar
          </Button>
        </div>
      </div>
    </div>
  );
};

// History Card Component
const HistoryCard = ({ order }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="bg-white rounded-lg border shadow-sm p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="font-medium text-sm">{order.customer_name}</span>
        <span className="text-xs text-muted-foreground">{formatTime(order.delivered_at || order.updated_at || order.created_at)}</span>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          {PAYMENT_ICONS[order.payment_method] && React.createElement(PAYMENT_ICONS[order.payment_method], { className: "h-3 w-3" })}
          <span>{PAYMENT_LABELS[order.payment_method]}</span>
          <span>• {order.items?.length || 0} itens</span>
        </div>
        <span className="text-sm font-bold text-brand-600">{formatCurrency(order.total)}</span>
      </div>
      {/* Items expandable */}
      <button 
        onClick={() => setExpanded(!expanded)} 
        className="text-xs text-brand-600 mt-1 hover:underline"
      >
        {expanded ? 'Ocultar itens ▲' : 'Ver itens ▼'}
      </button>
      {expanded && (
        <div className="mt-2 pt-2 border-t space-y-1">
          {order.items?.map((item, idx) => (
            <div key={`${order.id}-hist-item-${idx}`} className="flex justify-between text-xs">
              <span className="text-muted-foreground">{item.quantity}x {item.name}</span>
              <span>{formatCurrency(item.price * item.quantity)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Stock Item Component
const StockItem = ({ item, onUpdate }) => {
  const [qty, setQty] = useState(item.quantity);
  const [updating, setUpdating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(item.quantity.toString());
  const inputRef = useRef(null);

  const handleUpdate = async (newQty) => {
    if (newQty < 0) return;
    setUpdating(true);
    setQty(newQty);
    await onUpdate(item.menu_item_id, newQty);
    setUpdating(false);
  };

  const handleEditClick = () => {
    setEditValue(qty.toString());
    setIsEditing(true);
    setTimeout(() => inputRef.current?.select(), 50);
  };

  const handleEditSubmit = () => {
    const newQty = parseInt(editValue) || 0;
    if (newQty >= 0) {
      handleUpdate(newQty);
    }
    setIsEditing(false);
  };

  const handleEditKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleEditSubmit();
    } else if (e.key === 'Escape') {
      setIsEditing(false);
      setEditValue(qty.toString());
    }
  };

  return (
    <div className={`flex items-center justify-between p-2 rounded-lg border ${item.low_stock ? 'border-red-200 bg-red-50' : 'border-border'}`}>
      <div className="flex items-center gap-1 flex-1 min-w-0">
        {item.low_stock && <AlertTriangle className="h-3 w-3 text-red-500 shrink-0" />}
        <span className="text-xs font-medium truncate">{item.name}</span>
      </div>
      <div className="flex items-center gap-1 ml-1">
        <Button size="icon" variant="outline" className="h-6 w-6" onClick={() => handleUpdate(qty - 1)} disabled={updating || qty <= 0}>
          <Minus className="h-3 w-3" />
        </Button>
        {isEditing ? (
          <input
            ref={inputRef}
            type="number"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleEditSubmit}
            onKeyDown={handleEditKeyDown}
            className="w-12 h-6 text-center text-xs font-bold border rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
            min="0"
            autoFocus
          />
        ) : (
          <button 
            onClick={handleEditClick}
            className="min-w-10 max-w-16 px-1 h-6 text-center text-xs font-bold hover:bg-gray-100 rounded cursor-pointer transition-colors truncate"
            title={`${qty} — clique para editar`}
          >
            {qty > 99999 ? new Intl.NumberFormat('pt-BR', { notation: 'compact' }).format(qty) : qty}
          </button>
        )}
        <Button size="icon" variant="outline" className="h-6 w-6" onClick={() => handleUpdate(qty + 1)} disabled={updating}>
          <Plus className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
};

// Add Item Dialog
const AddItemDialog = ({ isOpen, onClose, onAdd }) => {
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState(10);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (name.trim()) {
      onAdd({ name: name.trim(), category: 'Ingredientes', quantity });
      setName('');
      setQuantity(10);
      onClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[90vw] sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-base">Adicionar Item</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label className="text-xs">Nome do Item</Label>
            <Input placeholder="Ex: Leite (litro)" value={name} onChange={(e) => setName(e.target.value)} required className="h-9" />
          </div>
          <div>
            <Label className="text-xs">Quantidade</Label>
            <Input type="number" value={quantity} onChange={(e) => setQuantity(parseInt(e.target.value) || 0)} min="0" className="h-9" />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
            <Button type="submit" size="sm" className="bg-brand-600 hover:bg-brand-700">Adicionar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

// PIX Proof Dialog
const PixProofDialog = ({ isOpen, onClose, order }) => {
  if (!order) return null;
  
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[95vw] sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">Comprovante PIX - {order.customer_name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="bg-secondary/50 rounded-lg p-3">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Itens</span>
              <span>{order.items?.length || 0}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total</span>
              <span className="font-bold text-brand-600">{formatCurrency(order.total)}</span>
            </div>
          </div>
          {order.pix_proof ? (
            <img 
              src={order.pix_proof} 
              alt="Comprovante PIX" 
              className="w-full max-h-[50vh] object-contain rounded-lg border"
            />
          ) : (
            <div className="bg-gray-100 rounded-lg p-8 text-center text-muted-foreground">
              <Image className="h-12 w-12 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Comprovante não enviado</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const KitchenPage = () => {
  const { store } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('pedidos');
  const [orders, setOrders] = useState([]);
  // Bell rings when a new order arrives (received status only)
  const newOrdersForBell = orders.filter((o) => o.status === 'received');
  const { enabled: bellEnabled, toggle: toggleBell } = useKitchenBell(newOrdersForBell);
  const [pendingPixOrders, setPendingPixOrders] = useState([]);
  const [historyOrders, setHistoryOrders] = useState([]);
  const [stats, setStats] = useState({ pending: 0, preparing: 0, ready: 0 });
  const [salesData, setSalesData] = useState({ shifts: { morning: { count: 0, by_payment: {} }, afternoon: { count: 0, by_payment: {} } }, order_count: 0 });
  const [stock, setStock] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [proofDialogOrder, setProofDialogOrder] = useState(null);
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [clearPassword, setClearPassword] = useState('');
  const [clickCount, setClickCount] = useState(0);
  const [isClearing, setIsClearing] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [prazoDebts, setPrazoDebts] = useState({ debts: [], total_prazo: 0 });
  const [showPrazoPayDialog, setShowPrazoPayDialog] = useState(false);
  const [selectedPrazoCustomer, setSelectedPrazoCustomer] = useState(null);
  const [prazoPassword, setPrazoPassword] = useState('');
  const [isPaying, setIsPaying] = useState(false);
  // Adicionais and Menu states
  const [adicionais, setAdicionais] = useState([]);
  const [showAdicionalDialog, setShowAdicionalDialog] = useState(false);
  const [newAdicional, setNewAdicional] = useState({ name: '', price: '' });
  const [editingAdicional, setEditingAdicional] = useState(null);
  const [menuItems, setMenuItems] = useState([]);
  const [showMenuDialog, setShowMenuDialog] = useState(false);
  const [newMenuItem, setNewMenuItem] = useState({ 
    name: '', description: '', price: '', category: 'doces',
    ncm: '', csosn: '', cfop: '', codigo_barras: ''
  });
  const [editingMenuItem, setEditingMenuItem] = useState(null);
  const [showFiscalFields, setShowFiscalFields] = useState(false);
  // Prazo customers state
  const [prazoCustomers, setPrazoCustomers] = useState([]);
  const [showPrazoCustomerDialog, setShowPrazoCustomerDialog] = useState(false);
  const [newPrazoCustomer, setNewPrazoCustomer] = useState({ name: '', phone: '', notes: '' });
  // Cash drawer state
  const [cashDrawer, setCashDrawer] = useState({ cash_in: 0, withdrawals: 0, current_balance: 0, withdrawal_history: [] });
  const [showWithdrawDialog, setShowWithdrawDialog] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawCategory, setWithdrawCategory] = useState('outros');
  const [withdrawDescription, setWithdrawDescription] = useState('');
  // Cash balance adjustment state
  const [showCashBalanceDialog, setShowCashBalanceDialog] = useState(false);
  const [newCashBalance, setNewCashBalance] = useState('');
  // PIX manual adjustments state
  const [pixAdjustments, setPixAdjustments] = useState({ adjustments: [], total_added: 0 });
  const [showPixAdjustDialog, setShowPixAdjustDialog] = useState(false);
  const [pixAdjustAmount, setPixAdjustAmount] = useState('');
  const [pixAdjustDescription, setPixAdjustDescription] = useState('');
  // Add credit dialog state
  const [showAddCreditDialog, setShowAddCreditDialog] = useState(false);
  const [creditCustomer, setCreditCustomer] = useState(null);
  const [creditAmount, setCreditAmount] = useState('');
  const [creditPaymentMethod, setCreditPaymentMethod] = useState('cash');
  // Edit customer dialog state
  const [showEditCustomerDialog, setShowEditCustomerDialog] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [editCustomerData, setEditCustomerData] = useState({ name: '', phone: '', notes: '' });
  // Partial payment (abater) dialog state
  const [showAbaterDialog, setShowAbaterDialog] = useState(false);
  const [abaterCustomer, setAbaterCustomer] = useState(null);
  const [abaterAmount, setAbaterAmount] = useState('');
  // Payment method state for prazo payments
  const [prazoPaymentMethod, setPrazoPaymentMethod] = useState('cash');
  const [abaterPaymentMethod, setAbaterPaymentMethod] = useState('cash');
  const [prazoSearchTerm, setPrazoSearchTerm] = useState(''); // Search term for prazo customers
  
  // Prazo payment history state
  const [prazoPaymentHistory, setPrazoPaymentHistory] = useState([]);
  const [showPrazoHistory, setShowPrazoHistory] = useState(false);
  
  const prevOrderCount = useRef(0);
  const hasSeededOrderCountRef = useRef(false);
  const { theme: uiTheme } = useTheme();
  const isDarkKitchen = uiTheme === 'dark';
  const audioRef = useRef(null);
  const alarmIntervalRef = useRef(null);
  const [newOrderAlert, setNewOrderAlert] = useState(null); // { orders: [...], open: bool }

  // Initialize audio: LOUD, repeating alert until dismissed
  useEffect(() => {
    const playAlarmBurst = () => {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        // Play a 3-note ascending alert twice — impossible to miss
        [880, 1175, 1568, 880, 1175, 1568].forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain); gain.connect(ctx.destination);
          osc.frequency.value = freq;
          osc.type = 'square';
          const start = ctx.currentTime + i * 0.18;
          gain.gain.setValueAtTime(0.4, start);
          gain.gain.exponentialRampToValueAtTime(0.01, start + 0.16);
          osc.start(start);
          osc.stop(start + 0.16);
        });
      } catch (e) { /* audio unsupported */ }
    };
    audioRef.current = { play: playAlarmBurst };
  }, []);

  // Start looping alarm until user dismisses
  const startAlarmLoop = useCallback(() => {
    if (!soundEnabled || alarmIntervalRef.current) return;
    audioRef.current?.play();
    alarmIntervalRef.current = setInterval(() => {
      audioRef.current?.play();
    }, 2500);
  }, [soundEnabled]);

  const stopAlarmLoop = useCallback(() => {
    if (alarmIntervalRef.current) {
      clearInterval(alarmIntervalRef.current);
      alarmIntervalRef.current = null;
    }
  }, []);

  // Cleanup interval on unmount
  useEffect(() => () => stopAlarmLoop(), [stopAlarmLoop]);

  // Legacy short beep (kept for status-change use)
  const playNewOrderSound = useCallback(() => {
    if (soundEnabled && audioRef.current) {
      try { audioRef.current.play(); } catch (e) { /* ignore */ }
    }
  }, [soundEnabled]);

  const fetchData = useCallback(async (showToast = false) => {
    try {
      const requests = [
        axios.get(`${API}/orders/${store}`),
        axios.get(`${API}/kitchen/${store}/stats`),
        axios.get(`${API}/cash/${store}/today`),
        axios.get(`${API}/stock/${store}`),
        axios.get(`${API}/orders/${store}/pending-pix`),
        axios.get(`${API}/orders/${store}/history`),
        axios.get(`${API}/prazo/debts?store=${store}`),  // Fetch prazo debts for this store only
        axios.get(`${API}/kitchen/adicionais`),  // Fetch adicionais
        axios.get(`${API}/kitchen/menu/${store}`),  // Fetch menu items for this store
        axios.get(`${API}/prazo/customers?store=${store}`),  // Fetch prazo customers for this store
        axios.get(`${API}/cash/${store}/drawer`),  // Fetch cash drawer status
        axios.get(`${API}/pix-adjustments/${store}`),  // Fetch PIX manual adjustments
        axios.get(`${API}/prazo/payments-history?store=${store}&limit=50`)  // Fetch prazo payment history
      ];
      
      // Use allSettled so a single failure doesn't kill the whole refresh (offline-friendly)
      const settled = await Promise.allSettled(requests);
      const anyFailed = settled.some((r) => r.status === 'rejected');
      const isOffline = typeof navigator !== 'undefined' && navigator.onLine === false;
      if (anyFailed && !isOffline) {
        // genuine server error
        throw new Error('partial-failure');
      }
      const data = (i) => settled[i].status === 'fulfilled' ? settled[i].value : null;
      const ordersRes = data(0), statsRes = data(1), cashRes = data(2), stockRes = data(3),
            pixRes = data(4), historyRes = data(5), prazoDebtsRes = data(6), adicionaisRes = data(7),
            menuRes = data(8), prazoCustomersRes = data(9), cashDrawerRes = data(10),
            pixAdjRes = data(11), prazoHistoryRes = data(12);
      
      if (ordersRes && pixRes) {
        const newOrders = ordersRes.data.orders.filter(o => !['delivered', 'pending_payment', 'payment_rejected'].includes(o.status));
        const newPendingCount = newOrders.filter(o => o.status === 'received').length + pixRes.data.orders.length;
        if (hasSeededOrderCountRef.current && newPendingCount > prevOrderCount.current) {
          // Detected a NEW incoming order → capture the freshest received ones
          const receivedNow = newOrders
            .filter(o => o.status === 'received')
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
          const brand = receivedNow.slice(0, newPendingCount - prevOrderCount.current);
          setNewOrderAlert({ orders: brand.length ? brand : receivedNow.slice(0, 1), open: true });
          startAlarmLoop();
          toast.info('Novo pedido chegou!', { duration: 5000 });
        }
        prevOrderCount.current = newPendingCount;
        hasSeededOrderCountRef.current = true;
        setOrders(newOrders);
        setPendingPixOrders(pixRes.data.orders);
      }
      if (statsRes) setStats(statsRes.data);
      if (cashRes) setSalesData(cashRes.data);
      if (stockRes) setStock(stockRes.data.stock);
      if (historyRes) setHistoryOrders(historyRes.data.orders);
      
      // Set prazo debts for this store
      if (prazoDebtsRes) {
        setPrazoDebts(prazoDebtsRes.data);
      }
      
      // Set adicionais
      if (adicionaisRes) {
        setAdicionais(adicionaisRes.data.adicionais || []);
      }
      
      // Set menu items
      if (menuRes) {
        setMenuItems(menuRes.data.items || []);
      }
      
      // Set prazo customers
      if (prazoCustomersRes) {
        setPrazoCustomers(prazoCustomersRes.data.customers || []);
      }
      
      // Set cash drawer
      if (cashDrawerRes) {
        setCashDrawer(cashDrawerRes.data);
      }
      
      // Set PIX adjustments
      if (pixAdjRes) {
        setPixAdjustments(pixAdjRes.data);
      }
      
      // Set prazo payment history
      if (prazoHistoryRes) {
        setPrazoPaymentHistory(prazoHistoryRes.data.payments || []);
      }
      
      if (showToast && !isOffline) toast.success('Atualizado');
      if (showToast && isOffline) toast.info('Offline · usando dados em cache');
    } catch (error) {
      const isOffline = typeof navigator !== 'undefined' && navigator.onLine === false;
      if (!isOffline) toast.error('Erro ao carregar');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [store, playNewOrderSound]);

  useEffect(() => {
    if (store) {
      // Remember last kitchen store opened so /equipe can pre-select it
      try { localStorage.setItem('ganoh_last_kitchen_store', store); } catch { /* ignore quota errors */ }
      // Initialize stock (best-effort, ignore failures when offline)
      axios.post(`${API}/stock/${store}/initialize`).catch(() => {}).then(() => fetchData());
      // Visibility-aware polling: 6s when active, paused when tab hidden
      // This dramatically reduces server load when multiple kitchens are open
      let interval = null;
      const startPolling = () => {
        if (interval) return;
        interval = setInterval(() => fetchData(), 6000);
      };
      const stopPolling = () => {
        if (interval) {
          clearInterval(interval);
          interval = null;
        }
      };
      const handleVisibility = () => {
        if (document.hidden) {
          stopPolling();
        } else {
          fetchData();
          startPolling();
        }
      };
      startPolling();
      document.addEventListener('visibilitychange', handleVisibility);
      return () => {
        stopPolling();
        document.removeEventListener('visibilitychange', handleVisibility);
      };
    }
  }, [store, fetchData]);

  const handleStatusChange = async (orderId, newStatus) => {
    try {
      await axios.patch(`${API}/orders/${store}/${orderId}/status`, { status: newStatus });
      fetchData();
      toast.success(STATUS_CONFIG[newStatus]?.label || newStatus);
    } catch (error) {
      toast.error('Erro');
    }
  };

  const handleDelete = async (orderId) => {
    try {
      // Delete permanently - won't appear in history or gestor
      await axios.delete(`${API}/orders/${store}/${orderId}`);
      fetchData();
      toast.success('Pedido apagado');
    } catch (error) {
      toast.error('Erro ao apagar');
    }
  };

  const handleApprovePayment = async (orderId) => {
    try {
      await axios.post(`${API}/orders/${store}/${orderId}/approve-payment`, { approved: true });
      fetchData();
      toast.success('Pagamento aprovado!');
    } catch (error) {
      toast.error('Erro ao aprovar');
    }
  };

  const handleRejectPayment = async (orderId) => {
    try {
      await axios.post(`${API}/orders/${store}/${orderId}/approve-payment`, { approved: false, rejection_reason: 'Comprovante inválido' });
      fetchData();
      toast.error('Pagamento recusado');
    } catch (error) {
      toast.error('Erro ao recusar');
    }
  };

  // Auto-verify PIX payment with AI
  const handleAutoVerifyPix = async (orderId) => {
    try {
      toast.loading('🤖 IA analisando comprovante...', { id: `verify-${orderId}` });
      
      const response = await axios.post(`${API}/orders/${store}/${orderId}/auto-verify-pix`);
      
      if (response.data.auto_approved) {
        toast.success(`✅ PIX aprovado automaticamente!\nPagador: ${response.data.payer_name}\nValor: R$ ${response.data.extracted_amount?.toFixed(2)}`, { 
          id: `verify-${orderId}`,
          duration: 5000 
        });
      } else {
        toast.error(`⚠️ Verificação manual necessária: ${response.data.message}`, { 
          id: `verify-${orderId}`,
          duration: 5000 
        });
      }
      
      fetchData();
      return response.data;
    } catch (error) {
      toast.error('Erro na verificação automática', { id: `verify-${orderId}` });
      return null;
    }
  };

  const handlePayPrazo = async () => {
    if (!selectedPrazoCustomer || !prazoPassword) return;
    
    setIsPaying(true);
    try {
      await axios.post(`${API}/prazo/pay-all/${encodeURIComponent(selectedPrazoCustomer.name)}`, {
        amount: selectedPrazoCustomer.total,
        password: prazoPassword,
        payment_method: prazoPaymentMethod
      });
      toast.success(`Pagamento de ${selectedPrazoCustomer.name} registrado! (${prazoPaymentMethod === 'cash' ? 'Dinheiro' : prazoPaymentMethod === 'pix' ? 'PIX' : prazoPaymentMethod === 'debit' ? 'Débito' : 'Crédito'})`);
      setShowPrazoPayDialog(false);
      setSelectedPrazoCustomer(null);
      setPrazoPassword('');
      setPrazoPaymentMethod('cash');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao registrar pagamento');
    } finally {
      setIsPaying(false);
    }
  };

  const handleStockUpdate = async (menuItemId, quantity) => {
    try {
      await axios.put(`${API}/stock/${store}/${menuItemId}`, { quantity });
    } catch (error) {
      toast.error('Erro');
    }
  };

  const handleAddItem = async (itemData) => {
    try {
      await axios.post(`${API}/stock/${store}/add`, itemData);
      fetchData();
      toast.success('Adicionado');
    } catch (error) {
      toast.error('Erro');
    }
  };

  // ==================== ADICIONAIS MANAGEMENT ====================
  const handleSaveAdicional = async () => {
    if (!newAdicional.name || !newAdicional.price) {
      toast.error('Preencha nome e preço');
      return;
    }
    try {
      const data = { name: newAdicional.name, price: parseFloat(newAdicional.price) };
      if (editingAdicional) {
        await axios.put(`${API}/kitchen/adicionais/${editingAdicional.id}`, data);
        toast.success('Adicional atualizado!');
      } else {
        await axios.post(`${API}/kitchen/adicionais`, data);
        toast.success('Adicional criado!');
      }
      setShowAdicionalDialog(false);
      setNewAdicional({ name: '', price: '' });
      setEditingAdicional(null);
      fetchData();
    } catch (error) {
      toast.error('Erro ao salvar adicional');
    }
  };

  const handleDeleteAdicional = async (adicionalId) => {
    try {
      await axios.delete(`${API}/kitchen/adicionais/${adicionalId}`);
      toast.success('Adicional removido');
      fetchData();
    } catch (error) {
      toast.error('Erro ao remover');
    }
  };

  // ==================== MENU MANAGEMENT ====================
  const handleSaveMenuItem = async () => {
    if (!newMenuItem.name || !newMenuItem.price) {
      toast.error('Preencha nome e preço');
      return;
    }
    try {
      const data = {
        name: newMenuItem.name,
        description: newMenuItem.description || '',
        price: parseFloat(newMenuItem.price),
        category: newMenuItem.category || 'doces',
        store: store,
        available: true,
        // Fiscal fields
        ncm: newMenuItem.ncm || '',
        csosn: newMenuItem.csosn || '',
        cfop: newMenuItem.cfop || '',
        codigo_barras: newMenuItem.codigo_barras || ''
      };
      if (editingMenuItem) {
        await axios.put(`${API}/kitchen/menu/${editingMenuItem.id}`, { ...editingMenuItem, ...data });
        toast.success('Item atualizado!');
      } else {
        await axios.post(`${API}/kitchen/menu`, data);
        toast.success('Item criado!');
      }
      setShowMenuDialog(false);
      setNewMenuItem({ name: '', description: '', price: '', category: 'doces', ncm: '', csosn: '', cfop: '', codigo_barras: '' });
      setEditingMenuItem(null);
      setShowFiscalFields(false);
      fetchData();
    } catch (error) {
      toast.error('Erro ao salvar item');
    }
  };

  const handleDeleteMenuItem = async (itemId) => {
    try {
      await axios.delete(`${API}/kitchen/menu/${itemId}`);
      toast.success('Item removido');
      fetchData();
    } catch (error) {
      toast.error('Erro ao remover');
    }
  };

  // ==================== PRAZO CUSTOMERS MANAGEMENT ====================
  const handleSavePrazoCustomer = async () => {
    if (!newPrazoCustomer.name) {
      toast.error('Preencha o nome do cliente');
      return;
    }
    try {
      await axios.post(`${API}/kitchen/prazo/customers`, {
        ...newPrazoCustomer,
        store: store  // Include the current store
      });
      toast.success('Cliente cadastrado!');
      setShowPrazoCustomerDialog(false);
      setNewPrazoCustomer({ name: '', phone: '', notes: '' });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao cadastrar');
    }
  };

  const handleDeletePrazoCustomer = async (customerId) => {
    try {
      await axios.delete(`${API}/kitchen/prazo/customers/${customerId}`);
      toast.success('Cliente removido');
      fetchData();
    } catch (error) {
      toast.error('Erro ao remover');
    }
  };

  const handleEditCustomer = (customer) => {
    setEditingCustomer(customer);
    setEditCustomerData({
      name: customer.name || '',
      phone: customer.phone || '',
      notes: customer.notes || ''
    });
    setShowEditCustomerDialog(true);
  };

  const handleSaveEditCustomer = async () => {
    if (!editCustomerData.name) {
      toast.error('Nome é obrigatório');
      return;
    }
    try {
      await axios.put(`${API}/kitchen/prazo/customers/${editingCustomer.id}`, editCustomerData);
      toast.success('Cliente atualizado!');
      setShowEditCustomerDialog(false);
      setEditingCustomer(null);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar');
    }
  };

  // WhatsApp charge functions
  const handleSendWhatsApp = async (customerName) => {
    try {
      toast.loading('Gerando mensagem...', { id: 'whatsapp' });
      const response = await axios.get(`${API}/prazo/charge-message/${encodeURIComponent(customerName)}`);
      toast.dismiss('whatsapp');
      // Open WhatsApp with pre-filled message
      const whatsappUrl = response.data.whatsapp_url;
      window.open(whatsappUrl, '_blank');
      toast.success('WhatsApp aberto com a mensagem!');
    } catch (error) {
      toast.dismiss('whatsapp');
      const errorMsg = error.response?.data?.detail || 'Erro ao gerar mensagem';
      if (errorMsg.includes('telefone')) {
        toast.error(`${customerName}: Sem telefone cadastrado! Cadastre na aba Prazo.`);
      } else {
        toast.error(errorMsg);
      }
    }
  };

  const handleChargeAllPrazo = async () => {
    try {
      toast.loading('Gerando mensagens...', { id: 'charge-all' });
      const response = await axios.get(`${API}/prazo/charge-messages?store=${store}`);
      toast.dismiss('charge-all');
      
      if (response.data.success && response.data.customers?.length > 0) {
        // Open WhatsApp for each customer with a small delay
        for (let i = 0; i < response.data.customers.length; i++) {
          const customer = response.data.customers[i];
          if (customer.whatsapp_url) {
            window.open(customer.whatsapp_url, '_blank');
            if (i < response.data.customers.length - 1) {
              await new Promise(r => setTimeout(r, 500)); // Small delay between opens
            }
          }
        }
        toast.success(`${response.data.customers.length} conversa(s) do WhatsApp abertas!`);
        if (response.data.no_phone?.length > 0) {
          toast.warning(`${response.data.no_phone.length} cliente(s) sem telefone`);
        }
      } else if (response.data.no_phone?.length > 0) {
        toast.error(`Todos os ${response.data.no_phone.length} cliente(s) estão sem telefone cadastrado`);
      } else {
        toast.info('Nenhum cliente para cobrar');
      }
    } catch (error) {
      toast.error('Erro ao gerar mensagens', { id: 'charge-all' });
    }
  };

  const handleAddCredit = (customer) => {
    setCreditCustomer(customer);
    setCreditAmount('');
    setShowAddCreditDialog(true);
  };

  const handleConfirmAddCredit = async () => {
    if (!creditAmount || isNaN(parseFloat(creditAmount)) || parseFloat(creditAmount) <= 0) {
      toast.error('Digite um valor válido');
      return;
    }
    
    try {
      const response = await axios.post(`${API}/prazo/customers/${creditCustomer.id}/add-credit`, {
        amount: parseFloat(creditAmount),
        payment_method: creditPaymentMethod,
      });
      toast.success(response.data.message, { duration: 5000 });
      setShowAddCreditDialog(false);
      setCreditCustomer(null);
      setCreditAmount('');
      setCreditPaymentMethod('cash');
      fetchData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Erro ao adicionar crédito');
    }
  };

  const handleDeletePrazoDebt = async (customerName) => {
    const password = prompt(`Apagar dívida de ${customerName}?\n\nDigite a senha do Prazo para confirmar:`);
    if (!password) return;
    
    try {
      const response = await axios.delete(`${API}/prazo/debt/${encodeURIComponent(customerName)}?password=${encodeURIComponent(password)}`);
      toast.success(response.data.message);
      fetchData();
    } catch (error) {
      if (error.response?.status === 403) {
        toast.error('Senha incorreta');
      } else {
        toast.error('Erro ao apagar dívida');
      }
    }
  };

  // Handler for partial payment (Abater)
  const [abaterPassword, setAbaterPassword] = useState('');
  
  const handleConfirmAbater = async () => {
    if (!abaterCustomer || !abaterAmount || parseFloat(abaterAmount) <= 0) {
      toast.error('Digite um valor válido');
      return;
    }
    
    if (!abaterPassword) {
      toast.error('Digite a senha');
      return;
    }
    
    if (parseFloat(abaterAmount) > abaterCustomer.total) {
      toast.error(`Valor maior que a dívida total (${formatCurrency(abaterCustomer.total)})`);
      return;
    }
    
    try {
      const response = await axios.post(`${API}/prazo/abater/${encodeURIComponent(abaterCustomer.name)}`, {
        amount: parseFloat(abaterAmount),
        password: abaterPassword,
        payment_method: abaterPaymentMethod,
        store
      });
      const methodLabel = abaterPaymentMethod === 'cash' ? 'Dinheiro' : abaterPaymentMethod === 'pix' ? 'PIX' : abaterPaymentMethod === 'debit' ? 'Débito' : abaterPaymentMethod === 'saldo' ? 'Saldo a Favor' : 'Crédito';
      toast.success(`${response.data.message} (${methodLabel})`);
      setShowAbaterDialog(false);
      setAbaterCustomer(null);
      setAbaterAmount('');
      setAbaterPassword('');
      setAbaterPaymentMethod('cash');
      fetchData();
    } catch (error) {
      if (error.response?.status === 403) {
        toast.error('Senha incorreta');
      } else if (error.response?.data?.detail) {
        toast.error(error.response.data.detail);
      } else {
        toast.error('Erro ao processar pagamento parcial');
      }
    }
  };

  const handleCashWithdraw = async () => {
    if (!withdrawAmount || isNaN(parseFloat(withdrawAmount)) || parseFloat(withdrawAmount) <= 0) {
      toast.error('Digite um valor válido');
      return;
    }
    
    if (parseFloat(withdrawAmount) > cashDrawer.current_balance) {
      toast.error('Saldo insuficiente no caixa');
      return;
    }
    
    try {
      const response = await axios.post(`${API}/cash/${store}/withdraw`, {
        amount: parseFloat(withdrawAmount),
        category: withdrawCategory,
        description: withdrawDescription || null
      });
      
      if (response.data.success) {
        toast.success(`Retirada de R$ ${parseFloat(withdrawAmount).toFixed(2)} realizada!`);
        if (response.data.expense_created) {
          toast.info('Gasto de VT registrado automaticamente');
        }
        setShowWithdrawDialog(false);
        setWithdrawAmount('');
        setWithdrawCategory('outros');
        setWithdrawDescription('');
        fetchData();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao retirar do caixa');
    }
  };

  const handleSetCashBalance = () => {
    setNewCashBalance(cashDrawer.initial_balance?.toString() || '0');
    setShowCashBalanceDialog(true);
  };

  const handleConfirmCashBalance = async () => {
    const value = parseFloat(newCashBalance);
    if (isNaN(value) || value < 0) {
      toast.error('Digite um valor válido (maior ou igual a zero)');
      return;
    }
    
    try {
      const currentBalance = cashDrawer.initial_balance || 0;
      const response = await axios.post(`${API}/cash/${store}/set-balance`, {
        balance: value,
        notes: `Ajustado de R$ ${currentBalance.toFixed(2)} para R$ ${value.toFixed(2)}`
      });
      
      toast.success(`Saldo inicial ajustado para R$ ${value.toFixed(2)}`);
      setCashDrawer(response.data);
      setShowCashBalanceDialog(false);
      setNewCashBalance('');
    } catch (error) {
      toast.error('Erro ao ajustar saldo');
    }
  };

  const handleZeroCash = async () => {
    if (!window.confirm('Tem certeza que deseja ZERAR o caixa completamente?\n\nIsso irá:\n• Zerar o saldo inicial\n• Limpar histórico de retiradas')) {
      return;
    }
    
    try {
      // Reset entire cash drawer - set balance to 0 and clear history
      const response = await axios.post(`${API}/cash/${store}/reset`);
      
      toast.success('Caixa zerado completamente!');
      setCashDrawer(response.data);
    } catch (error) {
      toast.error('Erro ao zerar o caixa');
    }
  };

  // PIX Manual Adjustment functions
  const handleAddPixAdjustment = async () => {
    if (!pixAdjustAmount || isNaN(parseFloat(pixAdjustAmount)) || parseFloat(pixAdjustAmount) === 0) {
      toast.error('Digite um valor válido');
      return;
    }
    
    try {
      await axios.post(`${API}/pix-adjustments/add`, {
        store: store,
        amount: parseFloat(pixAdjustAmount),
        description: pixAdjustDescription || 'Ajuste manual PIX'
      });
      toast.success(`Ajuste de PIX de R$ ${parseFloat(pixAdjustAmount).toFixed(2)} adicionado!`);
      setShowPixAdjustDialog(false);
      setPixAdjustAmount('');
      setPixAdjustDescription('');
      fetchData();
    } catch (error) {
      toast.error('Erro ao adicionar ajuste de PIX');
    }
  };

  const handleRemovePixAdjustment = async (adjustmentId) => {
    try {
      await axios.delete(`${API}/pix-adjustments/${adjustmentId}`);
      toast.success('Ajuste de PIX removido!');
      fetchData();
    } catch (error) {
      toast.error('Erro ao remover ajuste de PIX');
    }
  };

  const receivedOrders = orders.filter(o => o.status === 'received');
  const preparingOrders = orders.filter(o => o.status === 'preparing');
  const readyOrders = orders.filter(o => o.status === 'ready');

  const bebidasStock = stock.filter(s => s.type === 'bebida');
  const ingredientesStock = stock.filter(s => s.type === 'ingrediente' || s.type === 'custom');
  const lowStockCount = stock.filter(s => s.low_stock).length;

  const morningShift = salesData.shifts?.morning || { count: 0, by_payment: {} };
  const afternoonShift = salesData.shifts?.afternoon || { count: 0, by_payment: {} };

  // Hidden clear button - requires 5 clicks on store name + password
  const handleStoreNameClick = () => {
    const newCount = clickCount + 1;
    setClickCount(newCount);
    if (newCount >= 5) {
      setShowClearDialog(true);
      setClickCount(0);
    }
    // Reset after 3 seconds
    setTimeout(() => setClickCount(0), 3000);
  };

  const handleClearStoreData = async () => {
    setIsClearing(true);
    try {
      await axios.post(`${API}/admin/clear-store/${store}?password=${clearPassword}`);
      toast.success('Dados da loja foram apagados!');
      setShowClearDialog(false);
      setClearPassword('');
      fetchData(true);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Senha incorreta');
    } finally {
      setIsClearing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center relative overflow-hidden" style={{ background: isDarkKitchen ? 'radial-gradient(ellipse at center, #0a1410 0%, #050805 60%, #000000 100%)' : 'linear-gradient(180deg, #f7f8f3 0%, #edf0e5 100%)' }}>
        {isDarkKitchen && <KitchenStage3D />}
        <div className="relative z-10 flex flex-col items-center gap-6">
          <div className="relative">
            <div className="w-16 h-16 border-4 border-transparent rounded-full animate-spin" style={{ borderTopColor: '#a8d96b', borderRightColor: '#a8d96b', filter: 'drop-shadow(0 0 24px rgba(168,217,107,0.6))' }} />
            <div className="absolute inset-0 w-16 h-16 border-4 border-transparent rounded-full animate-spin" style={{ borderBottomColor: 'rgba(168,217,107,0.3)', animationDirection: 'reverse', animationDuration: '2s' }} />
          </div>
          <div className="text-center">
            <p style={{ fontFamily: 'Bodoni Moda, serif', fontSize: '1.4rem', color: isDarkKitchen ? '#d4f0a4' : '#55831f', letterSpacing: '0.3em' }}>GANOH</p>
            <p style={{ fontFamily: 'Manrope, sans-serif', fontSize: '0.7rem', color: isDarkKitchen ? 'rgba(233,240,225,0.5)' : 'rgba(38,51,31,0.55)', letterSpacing: '0.4em', textTransform: 'uppercase', marginTop: 8 }}>Preparando cozinha</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${isDarkKitchen ? 'kitchen-cinematic' : 'kitchen-daylight'}`} data-testid="kitchen-page">
      {isDarkKitchen && <KitchenStage3D />}
      <Toaster position="top-center" richColors theme={isDarkKitchen ? 'dark' : 'light'} />
      
      {/* Header - Cinematic */}
      <header className="border-b sticky top-0 z-50 px-2 py-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button data-testid="kitchen-home-btn" variant="ghost" size="icon" className="h-9 w-9" onClick={() => navigate('/')}>
              <Home className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <div className="relative">
                <div className="absolute inset-0 rounded-full blur-md" style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.5), transparent 70%)' }} />
                <ChefHat className="relative h-5 w-5" style={{ color: '#a8d96b', filter: 'drop-shadow(0 0 8px rgba(168,217,107,0.6))' }} />
              </div>
              <span 
                data-testid="kitchen-store-name"
                className="font-bold text-sm cursor-pointer select-none" 
                onClick={handleStoreNameClick}
                style={{ fontSize: '1.05rem' }}
              >
                {STORE_NAMES[store]}
              </span>
              {/* Switch store dropdown — fix bug "alterar loja na cozinha" */}
              <Select
                value={store}
                onValueChange={(newStore) => {
                  if (newStore && newStore !== store) {
                    try { localStorage.setItem('ganoh_last_kitchen_store', newStore); } catch { /* ignore quota errors */ }
                    navigate(`/${newStore}/cozinha`);
                  }
                }}
              >
                <SelectTrigger
                  data-testid="kitchen-switch-store-btn"
                  aria-label="Trocar loja"
                  title="Trocar loja"
                  className="h-7 w-7 p-0 border border-[#a8d96b]/30 bg-[#a8d96b]/[0.06] hover:bg-[#a8d96b]/15 rounded-full flex items-center justify-center [&>svg]:hidden text-[#a8d96b]"
                >
                  <ArrowLeftRight className="h-3.5 w-3.5" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(STORE_NAMES).map(([id, name]) => (
                    <SelectItem
                      key={id}
                      value={id}
                      data-testid={`kitchen-switch-store-${id}`}
                    >
                      <span className="inline-flex items-center gap-2">
                        <MapPin className="h-3.5 w-3.5 text-[#a8d96b]" />
                        {name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span style={{ fontFamily: 'Bodoni Moda, serif', fontStyle: 'italic', color: 'rgba(233,240,225,0.45)', fontSize: '0.7rem', letterSpacing: '0.25em', textTransform: 'uppercase', marginLeft: 6 }}>· Cozinha</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button 
              variant={soundEnabled ? "default" : "outline"} 
              size="icon" 
              className={`h-8 w-8 ${soundEnabled ? 'bg-brand-600' : ''}`}
              onClick={() => setSoundEnabled(!soundEnabled)}
              title={soundEnabled ? "Som ativado" : "Som desativado"}
            >
              {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
            </Button>
            <ThemeToggle className="!h-8 !w-8" />
            <Button 
              variant={bellEnabled ? "default" : "outline"} 
              size="icon" 
              className={`h-8 w-8 ${bellEnabled ? 'bg-brand-600' : ''}`}
              onClick={toggleBell}
              data-testid="kitchen-bell-toggle"
              title={bellEnabled ? "Sino: ativado (toca a cada novo pedido)" : "Sino: desativado"}
            >
              {bellEnabled ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => { setIsRefreshing(true); fetchData(true); }} disabled={isRefreshing}>
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
        
        {/* Quick Stats */}
        <div className="grid grid-cols-4 gap-1 mt-2 text-center text-xs">
          <div className="bg-blue-100 rounded py-1">
            <span className="font-bold text-blue-700">{pendingPixOrders.length}</span>
            <span className="text-muted-foreground ml-1">PIX</span>
          </div>
          <div className="bg-gray-100 rounded py-1">
            <span className="font-bold text-gray-700">{stats.pending}</span>
            <span className="text-muted-foreground ml-1">Aguard.</span>
          </div>
          <div className="bg-amber-100 rounded py-1">
            <span className="font-bold text-amber-700">{stats.preparing}</span>
            <span className="text-muted-foreground ml-1">Prep.</span>
          </div>
          <div className="bg-brand-100 rounded py-1">
            <span className="font-bold text-brand-700">{stats.ready}</span>
            <span className="text-muted-foreground ml-1">Prontos</span>
          </div>
        </div>
      </header>

      <main className="p-2">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full h-9 grid-cols-8">
            <TabsTrigger value="pix" className="text-xs h-7 px-1">
              PIX {pendingPixOrders.length > 0 && <Badge className="ml-1 bg-blue-600 h-4 min-w-4 p-0 justify-center text-[10px]">{pendingPixOrders.length}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="pedidos" className="text-xs h-7 px-1">
              Pedidos {(stats.pending + stats.preparing) > 0 && <Badge className="ml-1 bg-brand-600 h-4 min-w-4 p-0 justify-center text-[10px]">{stats.pending + stats.preparing}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="vendas" className="text-xs h-7 px-1">Vendas</TabsTrigger>
            <TabsTrigger value="prazo" className="text-xs h-7 px-1">
              Prazo {prazoDebts.customer_count > 0 && <Badge className="ml-1 bg-amber-600 h-4 min-w-4 p-0 justify-center text-[10px]">{prazoDebts.customer_count}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="estoque" className="text-xs h-7 px-1">
              Est. {lowStockCount > 0 && <Badge variant="destructive" className="ml-1 h-4 min-w-4 p-0 justify-center text-[10px]">{lowStockCount}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="cardapio" className="text-xs h-7 px-1">Card.</TabsTrigger>
            <TabsTrigger value="adicionais" className="text-xs h-7 px-1">Adic.</TabsTrigger>
            <TabsTrigger value="historico" className="text-xs h-7 px-1">
              <History className="h-3 w-3" />
            </TabsTrigger>
          </TabsList>

          {/* PIX PENDENTE TAB */}
          <TabsContent value="pix" className="mt-2">
            {pendingPixOrders.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {pendingPixOrders.map(order => (
                  <PixPendingCard 
                    key={order.id} 
                    order={order} 
                    onApprove={handleApprovePayment}
                    onReject={handleRejectPayment}
                    onViewProof={setProofDialogOrder}
                    onRetryVerify={handleAutoVerifyPix}
                  />
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Smartphone className="h-10 w-10 mx-auto mb-2 opacity-30" />
                <p className="text-sm">Nenhum PIX pendente</p>
              </div>
            )}
          </TabsContent>

          {/* PEDIDOS TAB */}
          <TabsContent value="pedidos" className="mt-2">
            <div className="space-y-3">
              {/* Aguardando */}
              {receivedOrders.length > 0 && (
                <div>
                  <div className="flex items-center gap-1 mb-2 text-xs font-semibold text-gray-600">
                    <Clock className="h-3 w-3" /> Aguardando ({receivedOrders.length})
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {receivedOrders.map(order => (
                      <OrderCard key={order.id} order={order} onStatusChange={handleStatusChange} onDelete={handleDelete} />
                    ))}
                  </div>
                </div>
              )}

              {/* Preparando */}
              {preparingOrders.length > 0 && (
                <div>
                  <div className="flex items-center gap-1 mb-2 text-xs font-semibold text-amber-600">
                    <ChefHat className="h-3 w-3" /> Preparando ({preparingOrders.length})
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {preparingOrders.map(order => (
                      <OrderCard key={order.id} order={order} onStatusChange={handleStatusChange} onDelete={handleDelete} />
                    ))}
                  </div>
                </div>
              )}

              {/* Prontos */}
              {readyOrders.length > 0 && (
                <div>
                  <div className="flex items-center gap-1 mb-2 text-xs font-semibold text-brand-600">
                    <CheckCircle2 className="h-3 w-3" /> Prontos ({readyOrders.length})
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {readyOrders.map(order => (
                      <OrderCard key={order.id} order={order} onStatusChange={handleStatusChange} onDelete={handleDelete} />
                    ))}
                  </div>
                </div>
              )}

              {orders.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <Package className="h-10 w-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">Nenhum pedido</p>
                </div>
              )}
            </div>
          </TabsContent>

          {/* VENDAS TAB */}
          <TabsContent value="vendas" className="mt-2 space-y-3">
            {/* Turno Manhã */}
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center gap-2 mb-3">
                <Sun className="h-4 w-4 text-amber-500" />
                <span className="font-semibold text-sm">Manhã (06:00 - 14:00)</span>
                <div className="ml-auto text-right">
                  <Badge variant="secondary" className="mb-1">{morningShift.count} pedidos</Badge>
                  <p className="text-xs text-muted-foreground">{formatCurrency(morningShift.total || 0)}</p>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-2 text-center">
                <div className="bg-brand-50 rounded-lg p-2">
                  <Smartphone className="h-4 w-4 mx-auto text-brand-600" />
                  <p className="text-[10px] text-muted-foreground">PIX</p>
                  <p className="text-sm font-bold text-brand-600">{formatCurrency(morningShift.by_payment?.pix || 0)}</p>
                </div>
                <div className="bg-blue-50 rounded-lg p-2">
                  <CreditCard className="h-4 w-4 mx-auto text-blue-600" />
                  <p className="text-[10px] text-muted-foreground">Débito</p>
                  <p className="text-sm font-bold text-blue-600">{formatCurrency(morningShift.by_payment?.debit || 0)}</p>
                </div>
                <div className="bg-purple-50 rounded-lg p-2">
                  <CreditCard className="h-4 w-4 mx-auto text-purple-600" />
                  <p className="text-[10px] text-muted-foreground">Crédito</p>
                  <p className="text-sm font-bold text-purple-600">{formatCurrency(morningShift.by_payment?.credit || 0)}</p>
                </div>
                <div className="bg-green-50 rounded-lg p-2">
                  <Banknote className="h-4 w-4 mx-auto text-green-600" />
                  <p className="text-[10px] text-muted-foreground">Dinheiro</p>
                  <p className="text-sm font-bold text-green-600">{formatCurrency(morningShift.by_payment?.cash || 0)}</p>
                </div>
                <div className="bg-pink-50 rounded-lg p-2">
                  <Ticket className="h-4 w-4 mx-auto text-pink-600" />
                  <p className="text-[10px] text-muted-foreground">Voucher</p>
                  <p className="text-sm font-bold text-pink-600">{formatCurrency(morningShift.by_payment?.voucher || 0)}</p>
                </div>
              </div>
            </div>

            {/* Turno Tarde */}
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center gap-2 mb-3">
                <Moon className="h-4 w-4 text-indigo-500" />
                <span className="font-semibold text-sm">Tarde/Noite (14:00 - 22:00)</span>
                <div className="ml-auto text-right">
                  <Badge variant="secondary" className="mb-1">{afternoonShift.count} pedidos</Badge>
                  <p className="text-xs text-muted-foreground">{formatCurrency(afternoonShift.total || 0)}</p>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-2 text-center">
                <div className="bg-brand-50 rounded-lg p-2">
                  <Smartphone className="h-4 w-4 mx-auto text-brand-600" />
                  <p className="text-[10px] text-muted-foreground">PIX</p>
                  <p className="text-sm font-bold text-brand-600">{formatCurrency(afternoonShift.by_payment?.pix || 0)}</p>
                </div>
                <div className="bg-blue-50 rounded-lg p-2">
                  <CreditCard className="h-4 w-4 mx-auto text-blue-600" />
                  <p className="text-[10px] text-muted-foreground">Débito</p>
                  <p className="text-sm font-bold text-blue-600">{formatCurrency(afternoonShift.by_payment?.debit || 0)}</p>
                </div>
                <div className="bg-purple-50 rounded-lg p-2">
                  <CreditCard className="h-4 w-4 mx-auto text-purple-600" />
                  <p className="text-[10px] text-muted-foreground">Crédito</p>
                  <p className="text-sm font-bold text-purple-600">{formatCurrency(afternoonShift.by_payment?.credit || 0)}</p>
                </div>
                <div className="bg-green-50 rounded-lg p-2">
                  <Banknote className="h-4 w-4 mx-auto text-green-600" />
                  <p className="text-[10px] text-muted-foreground">Dinheiro</p>
                  <p className="text-sm font-bold text-green-600">{formatCurrency(afternoonShift.by_payment?.cash || 0)}</p>
                </div>
                <div className="bg-pink-50 rounded-lg p-2">
                  <Ticket className="h-4 w-4 mx-auto text-pink-600" />
                  <p className="text-[10px] text-muted-foreground">Voucher</p>
                  <p className="text-sm font-bold text-pink-600">{formatCurrency(afternoonShift.by_payment?.voucher || 0)}</p>
                </div>
              </div>
            </div>

            {/* Total do Dia - Premium readable */}
            <div className="kc-stat-hero kc-stat-hero--brand">
              <div className="kc-stat-hero__decor" />
              <div className="kc-stat-hero__main">
                <span className="kc-stat-hero__label">Total do Dia</span>
                <span className="kc-stat-hero__value" data-testid="vendas-total-dia">{formatCurrency(salesData.total || 0)}</span>
              </div>
              <div className="kc-stat-hero__side">
                <span className="kc-stat-hero__sublabel">Pedidos</span>
                <span className="kc-stat-hero__subvalue" data-testid="vendas-total-pedidos">{salesData.order_count || 0}</span>
              </div>
            </div>

            {/* Caixa (Dinheiro em Espécie) - Premium readable */}
            <div className="kc-stat-hero kc-stat-hero--cash">
              <div className="kc-stat-hero__decor" />
              <div className="kc-stat-hero__row">
                <div className="kc-stat-hero__main">
                  <span className="kc-stat-hero__label">
                    <Banknote className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />Caixa · Dinheiro
                  </span>
                  <span className="kc-stat-hero__value" data-testid="vendas-caixa-saldo">{formatCurrency(cashDrawer.current_balance || 0)}</span>
                </div>
                <div className="kc-stat-hero__actions">
                  <Button
                    size="sm"
                    className="kc-stat-btn"
                    onClick={handleSetCashBalance}
                    title="Ajustar saldo inicial"
                    data-testid="cash-edit-btn"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    className="kc-stat-btn"
                    onClick={() => setShowWithdrawDialog(true)}
                    disabled={(cashDrawer.current_balance || 0) <= 0}
                    data-testid="cash-withdraw-btn"
                  >
                    <Minus className="h-3.5 w-3.5 mr-1" /> Retirar
                  </Button>
                  <Button
                    size="sm"
                    className="kc-stat-btn kc-stat-btn--danger"
                    onClick={handleZeroCash}
                    disabled={(cashDrawer.current_balance || 0) <= 0}
                    title="Zerar caixa"
                    data-testid="cash-zero-btn"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <div className="kc-mini-grid">
                <div className="kc-mini">
                  <span className="kc-mini__label">Saldo Inicial</span>
                  <span className="kc-mini__value" data-testid="cash-initial">{formatCurrency(cashDrawer.initial_balance || 0)}</span>
                </div>
                <div className="kc-mini kc-mini--positive">
                  <span className="kc-mini__label">+ Vendas</span>
                  <span className="kc-mini__value" data-testid="cash-sales">+{formatCurrency(cashDrawer.total_cash_sales || 0)}</span>
                </div>
                <div className="kc-mini kc-mini--negative">
                  <span className="kc-mini__label">– Retiradas</span>
                  <span className="kc-mini__value" data-testid="cash-withdrawals">-{formatCurrency(cashDrawer.total_withdrawals || 0)}</span>
                </div>
              </div>
              <div className="kc-stat-hero__foot">
                Hoje: +{formatCurrency(cashDrawer.today_cash_in || 0)} entradas · -{formatCurrency(cashDrawer.today_withdrawals || 0)} retiradas
              </div>
              {cashDrawer.withdrawal_history?.length > 0 && (
                <div className="kc-list-block">
                  <p className="kc-list-block__title">Retiradas de hoje</p>
                  <div className="kc-list-block__body">
                    {cashDrawer.withdrawal_history.map((w, idx) => (
                      <div key={`wd-${idx}`} className="kc-list-row">
                        <span className="truncate">{w.category === 'vt' ? '🚌 VT' : '💵 Outros'} · {w.description}</span>
                        <span className="kc-list-row__value kc-list-row__value--neg">-{formatCurrency(w.amount)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* PIX Manual Adjustments - Premium readable */}
            <div className="kc-stat-hero kc-stat-hero--pix">
              <div className="kc-stat-hero__decor" />
              <div className="kc-stat-hero__row">
                <div className="kc-stat-hero__main">
                  <span className="kc-stat-hero__label">
                    <Smartphone className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />Ajustes Manuais PIX
                  </span>
                  <span className="kc-stat-hero__value" data-testid="pix-adjust-total">{formatCurrency(pixAdjustments.total_added || 0)}</span>
                </div>
                <div className="kc-stat-hero__actions">
                  <Button
                    size="sm"
                    className="kc-stat-btn"
                    onClick={() => setShowPixAdjustDialog(true)}
                    data-testid="pix-adjust-add-btn"
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar
                  </Button>
                </div>
              </div>
              <div className="kc-stat-hero__foot">Valores PIX recebidos fora de vendas (transferências, etc.)</div>
              {pixAdjustments.adjustments?.length > 0 && (
                <div className="kc-list-block">
                  <p className="kc-list-block__title">Ajustes de hoje</p>
                  <div className="kc-list-block__body">
                    {pixAdjustments.adjustments.map((adj, idx) => (
                      <div key={`adj-${idx}`} className="kc-list-row">
                        <span className="truncate flex-1">{adj.description}</span>
                        <span className="kc-list-row__value kc-list-row__value--pos">+{formatCurrency(adj.amount)}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="kc-list-row__remove"
                          onClick={() => handleRemovePixAdjustment(adj.id)}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </TabsContent>

          {/* PRAZO TAB - For all stores */}
          <TabsContent value="prazo" className="mt-2 space-y-3">
            {/* Header with buttons */}
            <div className="flex justify-between items-center flex-wrap gap-2">
              <h3 className="font-semibold text-sm">Clientes no Prazo</h3>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="text-blue-600 border-blue-600" onClick={() => setShowPrazoHistory(!showPrazoHistory)}>
                  <History className="h-3 w-3 mr-1" /> {showPrazoHistory ? 'Ocultar' : 'Histórico'}
                </Button>
                <Button size="sm" variant="outline" className="text-green-600 border-green-600" onClick={handleChargeAllPrazo}>
                  <MessageCircle className="h-3 w-3 mr-1" /> Cobrar Todos
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowPrazoCustomerDialog(true)}>
                  <UserPlus className="h-3 w-3 mr-1" /> Novo Cliente
                </Button>
              </div>
            </div>
            
            {/* Payment History Section */}
            {showPrazoHistory && (
              <div className="bg-green-50 rounded-xl p-3 border border-green-200">
                <h4 className="font-semibold text-sm text-green-800 mb-2 flex items-center gap-1">
                  <History className="h-4 w-4" /> Pagamentos Realizados ({prazoPaymentHistory.length})
                </h4>
                {prazoPaymentHistory.length > 0 ? (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {prazoPaymentHistory.map((payment, idx) => (
                      <div key={idx} className="flex items-center justify-between bg-white p-2 rounded border">
                        <div>
                          <p className="font-medium text-sm">{payment.customer_name}</p>
                          <p className="text-xs text-muted-foreground">
                            {payment.type === 'partial_payment' ? 'Abatimento' : 'Pagamento Total'} • {payment.payment_method === 'cash' ? 'Dinheiro' : payment.payment_method === 'pix' ? 'PIX' : payment.payment_method === 'debit' ? 'Débito' : 'Crédito'}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {new Date(payment.created_at).toLocaleDateString('pt-BR')} às {new Date(payment.created_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                          </p>
                        </div>
                        <span className="font-bold text-green-600">{formatCurrency(payment.amount)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-4">Nenhum pagamento registrado</p>
                )}
              </div>
            )}
            
            {/* Search bar for prazo customers */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Buscar cliente..."
                value={prazoSearchTerm}
                onChange={(e) => setPrazoSearchTerm(e.target.value)}
                className="pl-10 h-10"
                data-testid="prazo-search-input"
              />
              {prazoSearchTerm && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 transform -translate-y-1/2 h-8 w-8"
                  onClick={() => setPrazoSearchTerm('')}
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
            
            {/* Total Prazo */}
            <div className="bg-amber-600 text-white rounded-xl p-4">
              <div className="flex justify-between items-center">
                <div>
                  <p className="text-sm opacity-80">Total a Receber (Prazo)</p>
                  <p className="text-2xl font-bold">{formatCurrency(prazoDebts.total_prazo || 0)}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm opacity-80">Clientes</p>
                  <p className="text-xl font-bold">{prazoDebts.customer_count || 0}</p>
                </div>
              </div>
            </div>

            {/* Clientes cadastrados com crédito */}
            {prazoCustomers.length > 0 && (
              <div className="bg-blue-50 rounded-xl p-3 border border-blue-200">
                <h4 className="font-semibold text-sm text-blue-800 mb-2 flex items-center gap-1">
                  <DollarSign className="h-4 w-4" /> Clientes Cadastrados 
                  {prazoSearchTerm ? (
                    <span className="font-normal">
                      ({prazoCustomers.filter(c => c.name.toLowerCase().includes(prazoSearchTerm.toLowerCase())).length} de {prazoCustomers.length})
                    </span>
                  ) : (
                    <span className="font-normal">({prazoCustomers.length})</span>
                  )}
                </h4>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {prazoCustomers
                    .filter(customer => customer.name.toLowerCase().includes(prazoSearchTerm.toLowerCase()))
                    .map(customer => (
                    <div key={customer.id} className="flex items-center justify-between bg-white p-2 rounded border">
                      <div>
                        <p className="font-medium text-sm">{customer.name}</p>
                        <p className="text-xs text-muted-foreground">{customer.phone || 'Sem telefone'}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        {(customer.credit || 0) > 0 && (
                          <span className="font-bold text-green-600 text-xs bg-green-50 px-2 py-1 rounded">R$ {(customer.credit || 0).toFixed(2)}</span>
                        )}
                        <Button size="sm" variant="outline" className="h-7 w-7 p-0 text-blue-600 border-blue-600 hover:bg-blue-50" onClick={() => handleEditCustomer(customer)} title="Editar cliente">
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 px-2 text-green-600 border-green-600 hover:bg-green-50" onClick={() => handleAddCredit(customer)} title="Adicionar crédito">
                          <Plus className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 w-7 p-0 text-red-600 border-red-600 hover:bg-red-50" onClick={() => handleDeletePrazoCustomer(customer.id)} title="Excluir cliente">
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Lista de devedores */}
            {prazoDebts.debts?.length > 0 ? (
              <div className="space-y-2">
                <h4 className="font-semibold text-sm text-amber-700">
                  Débitos Pendentes
                  {prazoSearchTerm && (
                    <span className="text-xs font-normal ml-2">
                      (mostrando {prazoDebts.debts.filter(d => d.name.toLowerCase().includes(prazoSearchTerm.toLowerCase())).length} de {prazoDebts.debts.length})
                    </span>
                  )}
                </h4>
                {prazoDebts.debts
                  .filter(debt => debt.name.toLowerCase().includes(prazoSearchTerm.toLowerCase()))
                  .map((debt, idx) => (
                  <div key={idx} className="bg-white rounded-lg p-3 border shadow-sm">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">{debt.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {debt.order_count} pedido(s)
                          {!debt.phone && <span className="text-red-500 ml-1">(sem telefone)</span>}
                        </p>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="font-bold text-amber-600 mr-1">{formatCurrency(debt.total)}</span>
                        <Button 
                          size="sm" 
                          variant="outline"
                          className={`h-8 px-2 ${debt.phone ? 'text-green-600 border-green-600 hover:bg-green-50' : 'text-gray-400 border-gray-300 cursor-not-allowed'}`}
                          onClick={() => debt.phone && handleSendWhatsApp(debt.name)}
                          disabled={!debt.phone}
                          title={debt.phone ? "Enviar cobrança por WhatsApp" : "Cadastre o telefone na aba Prazo"}
                        >
                          <MessageCircle className="h-4 w-4" />
                        </Button>
                        <Button 
                          size="sm" 
                          variant="outline"
                          className="text-amber-600 border-amber-600 hover:bg-amber-50 h-8 px-2"
                          onClick={() => {
                            setAbaterCustomer(debt);
                            setAbaterAmount('');
                            setShowAbaterDialog(true);
                          }}
                          title="Abater valor parcial"
                        >
                          <Minus className="h-4 w-4 mr-1" /> Abater
                        </Button>
                        <Button 
                          size="sm" 
                          variant="outline"
                          className="text-green-600 border-green-600 hover:bg-green-50 h-8 px-2"
                          onClick={() => {
                            setSelectedPrazoCustomer(debt);
                            setShowPrazoPayDialog(true);
                          }}
                          title="Registrar pagamento total"
                        >
                          <Check className="h-4 w-4 mr-1" /> Pagar
                        </Button>
                        <Button 
                          size="sm" 
                          variant="outline"
                          className="text-red-600 border-red-600 hover:bg-red-50 h-8 px-2"
                          onClick={() => handleDeletePrazoDebt(debt.name)}
                          title="Apagar/zerar dívida"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    {/* Orders detail */}
                    <div className="mt-2 pt-2 border-t space-y-1">
                      {debt.orders.map((order, oidx) => (
                        <div key={oidx} className="flex justify-between text-xs text-muted-foreground">
                          <span>{new Date(order.date).toLocaleDateString('pt-BR')} - {order.items?.map(i => i.name).join(', ')}</span>
                          <span>{formatCurrency(order.total)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <CalendarClock className="h-10 w-10 mx-auto mb-2 opacity-30" />
                <p className="text-sm">Nenhum débito pendente</p>
              </div>
            )}
          </TabsContent>

          {/* ESTOQUE TAB */}
          <TabsContent value="estoque" className="mt-2 space-y-3">
            {/* Bebidas */}
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-sm flex items-center gap-1">
                  <Coffee className="h-4 w-4 text-amber-600" /> Bebidas
                </h3>
              </div>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {bebidasStock.map(item => (
                  <StockItem key={item.menu_item_id} item={item} onUpdate={handleStockUpdate} />
                ))}
                {bebidasStock.length === 0 && <p className="text-xs text-muted-foreground text-center py-2">Nenhuma bebida</p>}
              </div>
            </div>

            {/* Ingredientes */}
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-sm flex items-center gap-1">
                  <Droplets className="h-4 w-4 text-blue-600" /> Ingredientes
                </h3>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowAddDialog(true)}>
                  <Plus className="h-3 w-3 mr-1" /> Adicionar
                </Button>
              </div>
              <div className="space-y-1.5 max-h-52 overflow-y-auto">
                {ingredientesStock.map(item => (
                  <StockItem key={item.menu_item_id} item={item} onUpdate={handleStockUpdate} />
                ))}
                {ingredientesStock.length === 0 && <p className="text-xs text-muted-foreground text-center py-2">Nenhum ingrediente</p>}
              </div>
            </div>

            {lowStockCount > 0 && (
              <div className="bg-red-50 rounded-xl p-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-red-500" />
                <span className="text-xs text-red-700 font-medium">{lowStockCount} item(ns) com estoque baixo</span>
              </div>
            )}
          </TabsContent>

          {/* CARDÁPIO TAB */}
          <TabsContent value="cardapio" className="mt-2">
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm flex items-center gap-1">
                  <UtensilsCrossed className="h-4 w-4 text-brand-600" /> Cardápio
                </h3>
                <Button size="sm" variant="outline" onClick={() => { setEditingMenuItem(null); setNewMenuItem({ name: '', description: '', price: '', category: 'doces', ncm: '', csosn: '', cfop: '', codigo_barras: '' }); setShowFiscalFields(false); setShowMenuDialog(true); }}>
                  <Plus className="h-3 w-3 mr-1" /> Novo Item
                </Button>
              </div>
              <ScrollArea className="h-[55vh]">
                <div className="space-y-2 pr-2">
                  {menuItems.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <UtensilsCrossed className="h-8 w-8 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">Nenhum item personalizado</p>
                      <p className="text-xs">Adicione itens ao cardápio desta loja</p>
                    </div>
                  ) : (
                    menuItems.map(item => (
                      <div key={item.id} className="flex items-center justify-between p-2 border rounded-lg bg-gray-50 hover:bg-gray-100">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm">{item.name}</span>
                            <Badge variant="outline" className="text-[10px] h-4">{item.category}</Badge>
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            R$ {item.price?.toFixed(2)} {item.description && `• ${item.description}`}
                          </div>
                          {item.codigo && <span className="text-[10px] text-muted-foreground">Cód: {item.codigo}</span>}
                        </div>
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => { setEditingMenuItem(item); setNewMenuItem({ name: item.name, description: item.description || '', price: item.price?.toString() || '', category: item.category || 'doces', ncm: item.ncm || '', csosn: item.csosn || '', cfop: item.cfop || '', codigo_barras: item.codigo_barras || '' }); setShowFiscalFields(!!item.ncm || !!item.csosn); setShowMenuDialog(true); }}>
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-600" onClick={() => handleDeleteMenuItem(item.id)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          </TabsContent>

          {/* ADICIONAIS TAB */}
          <TabsContent value="adicionais" className="mt-2">
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm flex items-center gap-1">
                  <Plus className="h-4 w-4 text-green-600" /> Adicionais
                </h3>
                <Button size="sm" variant="outline" onClick={() => { setEditingAdicional(null); setNewAdicional({ name: '', price: '' }); setShowAdicionalDialog(true); }}>
                  <Plus className="h-3 w-3 mr-1" /> Novo Adicional
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                Adicionais como ovos, queijo, mel disponíveis para todos os itens.
              </p>
              <ScrollArea className="h-[50vh]">
                <div className="grid grid-cols-2 gap-2 pr-2">
                  {adicionais.length === 0 ? (
                    <div className="col-span-2 text-center py-8 text-muted-foreground">
                      <Plus className="h-8 w-8 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">Nenhum adicional cadastrado</p>
                    </div>
                  ) : (
                    adicionais.map(adicional => (
                      <div key={adicional.id} className="flex items-center justify-between p-2 border rounded-lg bg-green-50">
                        <div>
                          <p className="font-medium text-sm">{adicional.name}</p>
                          <p className="text-xs text-green-600">R$ {adicional.price?.toFixed(2)}</p>
                        </div>
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => { setEditingAdicional(adicional); setNewAdicional({ name: adicional.name, price: adicional.price?.toString() || '' }); setShowAdicionalDialog(true); }}>
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-red-600" onClick={() => handleDeleteAdicional(adicional.id)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          </TabsContent>

          {/* HISTÓRICO TAB */}
          <TabsContent value="historico" className="mt-2">
            <div className="bg-white rounded-xl p-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm flex items-center gap-1">
                  <History className="h-4 w-4 text-muted-foreground" /> Últimas 24h
                </h3>
                <Badge variant="secondary">{historyOrders.length} pedidos</Badge>
              </div>
              <ScrollArea className="h-[60vh]">
                <div className="space-y-2 pr-2">
                  {historyOrders.map(order => (
                    <HistoryCard key={order.id} order={order} />
                  ))}
                  {historyOrders.length === 0 && (
                    <div className="text-center py-8 text-muted-foreground">
                      <History className="h-10 w-10 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">Nenhum pedido nas últimas 24h</p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
          </TabsContent>
        </Tabs>
      </main>

      <AddItemDialog isOpen={showAddDialog} onClose={() => setShowAddDialog(false)} onAdd={handleAddItem} />
      <PixProofDialog isOpen={!!proofDialogOrder} onClose={() => setProofDialogOrder(null)} order={proofDialogOrder} />
      
      {/* Hidden Clear Data Dialog */}
      <Dialog open={showClearDialog} onOpenChange={setShowClearDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base text-red-600 flex items-center gap-2">
              <Trash2 className="h-4 w-4" />
              Limpar Dados da Loja
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Esta ação irá apagar <strong>todos os pedidos e histórico</strong> desta loja. Esta ação não pode ser desfeita.
            </p>
            <Input
              type="password"
              placeholder="Senha de administrador"
              value={clearPassword}
              onChange={(e) => setClearPassword(e.target.value)}
              className="h-9"
            />
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => { setShowClearDialog(false); setClearPassword(''); }}>
                Cancelar
              </Button>
              <Button 
                variant="destructive" 
                size="sm"
                className="flex-1" 
                onClick={handleClearStoreData}
                disabled={isClearing || !clearPassword}
              >
                {isClearing ? 'Apagando...' : 'Apagar'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prazo Payment Dialog */}
      <Dialog open={showPrazoPayDialog} onOpenChange={setShowPrazoPayDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base text-green-600 flex items-center gap-2">
              <Check className="h-4 w-4" />
              Registrar Pagamento
            </DialogTitle>
          </DialogHeader>
          {selectedPrazoCustomer && (
            <div className="space-y-3">
              <div className="bg-amber-50 rounded-lg p-3">
                <p className="font-medium">{selectedPrazoCustomer.name}</p>
                <p className="text-2xl font-bold text-amber-600">{formatCurrency(selectedPrazoCustomer.total)}</p>
                <p className="text-xs text-muted-foreground">{selectedPrazoCustomer.order_count} pedido(s) pendente(s)</p>
              </div>
              <div>
                <Label className="text-sm">Forma de Pagamento</Label>
                <div className="grid grid-cols-4 gap-1 mt-1">
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={prazoPaymentMethod === 'cash' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${prazoPaymentMethod === 'cash' ? 'bg-green-600' : ''}`}
                    onClick={() => setPrazoPaymentMethod('cash')}
                  >
                    <Banknote className="h-3 w-3 mr-1" /> Din
                  </Button>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={prazoPaymentMethod === 'pix' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${prazoPaymentMethod === 'pix' ? 'bg-green-600' : ''}`}
                    onClick={() => setPrazoPaymentMethod('pix')}
                  >
                    <Smartphone className="h-3 w-3 mr-1" /> PIX
                  </Button>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={prazoPaymentMethod === 'debit' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${prazoPaymentMethod === 'debit' ? 'bg-green-600' : ''}`}
                    onClick={() => setPrazoPaymentMethod('debit')}
                  >
                    <CreditCard className="h-3 w-3 mr-1" /> Débito
                  </Button>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={prazoPaymentMethod === 'credit' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${prazoPaymentMethod === 'credit' ? 'bg-green-600' : ''}`}
                    onClick={() => setPrazoPaymentMethod('credit')}
                  >
                    <CreditCard className="h-3 w-3 mr-1" /> Crédito
                  </Button>
                </div>
              </div>
              <div>
                <Label className="text-sm">Senha de confirmação</Label>
                <Input
                  type="password"
                  placeholder="Senha (1234)"
                  value={prazoPassword}
                  onChange={(e) => setPrazoPassword(e.target.value)}
                  className="h-9 mt-1"
                />
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => { setShowPrazoPayDialog(false); setPrazoPassword(''); setSelectedPrazoCustomer(null); setPrazoPaymentMethod('cash'); }}>
                  Cancelar
                </Button>
                <Button 
                  size="sm"
                  className="flex-1 bg-green-600 hover:bg-green-700" 
                  onClick={handlePayPrazo}
                  disabled={isPaying || !prazoPassword}
                >
                  {isPaying ? 'Processando...' : 'Confirmar Pagamento'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Adicional Dialog */}
      <Dialog open={showAdicionalDialog} onOpenChange={setShowAdicionalDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Plus className="h-4 w-4 text-green-600" />
              {editingAdicional ? 'Editar Adicional' : 'Novo Adicional'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Nome</Label>
              <Input
                value={newAdicional.name}
                onChange={(e) => setNewAdicional({ ...newAdicional, name: e.target.value })}
                placeholder="Ex: Ovo, Queijo, Mel"
                className="h-9"
              />
            </div>
            <div>
              <Label className="text-xs">Preço (R$)</Label>
              <Input
                type="number"
                step="0.01"
                value={newAdicional.price}
                onChange={(e) => setNewAdicional({ ...newAdicional, price: e.target.value })}
                placeholder="0.00"
                className="h-9"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => setShowAdicionalDialog(false)}>
                Cancelar
              </Button>
              <Button size="sm" className="flex-1 bg-green-600 hover:bg-green-700" onClick={handleSaveAdicional}>
                Salvar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Menu Item Dialog */}
      <Dialog open={showMenuDialog} onOpenChange={setShowMenuDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <UtensilsCrossed className="h-4 w-4 text-brand-600" />
              {editingMenuItem ? 'Editar Item' : 'Novo Item do Cardápio'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Nome</Label>
              <Input
                value={newMenuItem.name}
                onChange={(e) => setNewMenuItem({ ...newMenuItem, name: e.target.value })}
                placeholder="Ex: Açaí com Banana"
                className="h-9"
              />
            </div>
            <div>
              <Label className="text-xs">Descrição (opcional)</Label>
              <Input
                value={newMenuItem.description}
                onChange={(e) => setNewMenuItem({ ...newMenuItem, description: e.target.value })}
                placeholder="Descrição breve"
                className="h-9"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Preço (R$)</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={newMenuItem.price}
                  onChange={(e) => setNewMenuItem({ ...newMenuItem, price: e.target.value })}
                  placeholder="0.00"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Categoria</Label>
                <Select value={newMenuItem.category} onValueChange={(v) => setNewMenuItem({ ...newMenuItem, category: v })}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="doces">Doces</SelectItem>
                    <SelectItem value="salgados">Salgados</SelectItem>
                    <SelectItem value="bebidas">Bebidas</SelectItem>
                    <SelectItem value="sucos">Sucos</SelectItem>
                    <SelectItem value="acai">Açaí</SelectItem>
                    <SelectItem value="cafes">Cafés</SelectItem>
                    <SelectItem value="outros">Outros</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            {/* Fiscal Fields Toggle */}
            <Button 
              type="button" 
              variant="ghost" 
              size="sm" 
              className="w-full text-xs text-muted-foreground"
              onClick={() => setShowFiscalFields(!showFiscalFields)}
            >
              {showFiscalFields ? '▲ Ocultar campos fiscais' : '▼ Campos fiscais (NF-e)'}
            </Button>
            
            {/* Fiscal Fields */}
            {showFiscalFields && (
              <div className="bg-amber-50 rounded-lg p-3 space-y-2 border border-amber-200">
                <p className="text-[10px] text-amber-700 font-medium">Dados para Nota Fiscal Eletrônica</p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-[10px]">NCM</Label>
                    <Input
                      value={newMenuItem.ncm || ''}
                      onChange={(e) => setNewMenuItem({ ...newMenuItem, ncm: e.target.value })}
                      placeholder="21069090"
                      className="h-7 text-xs"
                    />
                  </div>
                  <div>
                    <Label className="text-[10px]">CSOSN</Label>
                    <Input
                      value={newMenuItem.csosn || ''}
                      onChange={(e) => setNewMenuItem({ ...newMenuItem, csosn: e.target.value })}
                      placeholder="0102"
                      className="h-7 text-xs"
                    />
                  </div>
                  <div>
                    <Label className="text-[10px]">CFOP</Label>
                    <Input
                      value={newMenuItem.cfop || ''}
                      onChange={(e) => setNewMenuItem({ ...newMenuItem, cfop: e.target.value })}
                      placeholder="5102"
                      className="h-7 text-xs"
                    />
                  </div>
                  <div>
                    <Label className="text-[10px]">Cód. Barras</Label>
                    <Input
                      value={newMenuItem.codigo_barras || ''}
                      onChange={(e) => setNewMenuItem({ ...newMenuItem, codigo_barras: e.target.value })}
                      placeholder="7891234567890"
                      className="h-7 text-xs"
                    />
                  </div>
                </div>
                <p className="text-[9px] text-amber-600">
                  NCM: Nomenclatura Comum do Mercosul | CSOSN: Simples Nacional | CFOP: Código Fiscal
                </p>
              </div>
            )}
            
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => setShowMenuDialog(false)}>
                Cancelar
              </Button>
              <Button size="sm" className="flex-1 bg-brand-600 hover:bg-brand-700" onClick={handleSaveMenuItem}>
                Salvar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prazo Customer Dialog */}
      <Dialog open={showPrazoCustomerDialog} onOpenChange={setShowPrazoCustomerDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <UserPlus className="h-4 w-4 text-amber-600" />
              Cadastrar Cliente Prazo
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Nome do Cliente</Label>
              <Input
                value={newPrazoCustomer.name}
                onChange={(e) => setNewPrazoCustomer({ ...newPrazoCustomer, name: e.target.value })}
                placeholder="Nome completo"
                className="h-9"
              />
            </div>
            <div>
              <Label className="text-xs">Telefone (opcional)</Label>
              <Input
                value={newPrazoCustomer.phone}
                onChange={(e) => setNewPrazoCustomer({ ...newPrazoCustomer, phone: e.target.value })}
                placeholder="(11) 99999-9999"
                className="h-9"
              />
            </div>
            <div>
              <Label className="text-xs">Observações (opcional)</Label>
              <Input
                value={newPrazoCustomer.notes}
                onChange={(e) => setNewPrazoCustomer({ ...newPrazoCustomer, notes: e.target.value })}
                placeholder="Ex: Academia, Personal"
                className="h-9"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => setShowPrazoCustomerDialog(false)}>
                Cancelar
              </Button>
              <Button size="sm" className="flex-1 bg-amber-600 hover:bg-amber-700" onClick={handleSavePrazoCustomer}>
                Cadastrar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Cash Withdrawal Dialog */}
      <Dialog open={showWithdrawDialog} onOpenChange={setShowWithdrawDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Banknote className="h-4 w-4 text-green-600" />
              Retirar do Caixa
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <p className="text-xs text-muted-foreground">Saldo disponível</p>
              <p className="text-xl font-bold text-green-600">{formatCurrency(cashDrawer.current_balance || 0)}</p>
            </div>
            
            <div>
              <Label className="text-xs">Valor a retirar (R$)</Label>
              <Input
                type="number"
                step="0.01"
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                placeholder="0.00"
                className="h-9"
              />
            </div>
            
            <div>
              <Label className="text-xs">Tipo de retirada</Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                <Button
                  type="button"
                  variant={withdrawCategory === 'vt' ? 'default' : 'outline'}
                  size="sm"
                  className={withdrawCategory === 'vt' ? 'bg-blue-600 hover:bg-blue-700' : ''}
                  onClick={() => setWithdrawCategory('vt')}
                >
                  🚌 Vale Transporte
                </Button>
                <Button
                  type="button"
                  variant={withdrawCategory === 'outros' ? 'default' : 'outline'}
                  size="sm"
                  className={withdrawCategory === 'outros' ? 'bg-gray-600 hover:bg-gray-700' : ''}
                  onClick={() => setWithdrawCategory('outros')}
                >
                  💵 Outros
                </Button>
              </div>
              {withdrawCategory === 'vt' && (
                <p className="text-xs text-blue-600 mt-1">* Será registrado automaticamente como gasto</p>
              )}
            </div>
            
            <div>
              <Label className="text-xs">Descrição (opcional)</Label>
              <Input
                value={withdrawDescription}
                onChange={(e) => setWithdrawDescription(e.target.value)}
                placeholder={withdrawCategory === 'vt' ? 'Ex: VT da semana' : 'Ex: Troco para cliente'}
                className="h-9"
              />
            </div>
            
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                setShowWithdrawDialog(false);
                setWithdrawAmount('');
                setWithdrawCategory('outros');
                setWithdrawDescription('');
              }}>
                Cancelar
              </Button>
              <Button 
                size="sm" 
                className="flex-1 bg-green-600 hover:bg-green-700" 
                onClick={handleCashWithdraw}
                disabled={!withdrawAmount || parseFloat(withdrawAmount) <= 0}
              >
                Confirmar Retirada
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Cash Balance Adjustment Dialog */}
      <Dialog open={showCashBalanceDialog} onOpenChange={setShowCashBalanceDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Pencil className="h-4 w-4 text-green-600" />
              Ajustar Saldo do Caixa
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-muted-foreground">Saldo inicial atual</p>
              <p className="text-xl font-bold">{formatCurrency(cashDrawer.initial_balance || 0)}</p>
            </div>
            
            <div>
              <Label className="text-sm">Novo saldo inicial (R$)</Label>
              <Input
                type="number"
                step="0.01"
                min="0"
                value={newCashBalance}
                onChange={(e) => setNewCashBalance(e.target.value)}
                placeholder="0.00"
                className="h-10 text-lg"
                autoFocus
              />
              <p className="text-xs text-muted-foreground mt-1">
                Este valor é o dinheiro que já estava no caixa. Não conta como venda.
              </p>
            </div>
            
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                setShowCashBalanceDialog(false);
                setNewCashBalance('');
              }}>
                Cancelar
              </Button>
              <Button 
                size="sm" 
                className="flex-1 bg-green-600 hover:bg-green-700" 
                onClick={handleConfirmCashBalance}
                disabled={!newCashBalance || parseFloat(newCashBalance) < 0}
              >
                Salvar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Credit Dialog */}
      <Dialog open={showAddCreditDialog} onOpenChange={setShowAddCreditDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-green-600" />
              Adicionar Crédito
            </DialogTitle>
          </DialogHeader>
          {creditCustomer && (
            <div className="space-y-4">
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="font-medium">{creditCustomer.name}</p>
                <p className="text-xs text-muted-foreground">{creditCustomer.phone || 'Sem telefone'}</p>
                <div className="mt-2 pt-2 border-t border-blue-200">
                  <p className="text-xs text-muted-foreground">Crédito atual</p>
                  <p className="text-lg font-bold text-green-600">{formatCurrency(creditCustomer.credit || 0)}</p>
                </div>
              </div>
              
              <div>
                <Label className="text-sm">Valor a adicionar (R$)</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={creditAmount}
                  onChange={(e) => setCreditAmount(e.target.value)}
                  placeholder="0.00"
                  className="h-10 text-lg"
                  autoFocus
                />
                <p className="text-[11px] text-muted-foreground mt-1.5 leading-tight">
                  💡 Se o cliente tiver pedidos prazo em aberto, o valor abate
                  automaticamente da dívida (do mais antigo p/ o mais recente).
                  Só o que sobrar entra como crédito.
                </p>
              </div>
              <div>
                <Label className="text-sm">Forma de pagamento</Label>
                <select
                  value={creditPaymentMethod}
                  onChange={(e) => setCreditPaymentMethod(e.target.value)}
                  className="w-full border rounded-md px-2 py-2 text-sm bg-background h-10"
                  data-testid="credit-payment-method"
                >
                  <option value="cash">Dinheiro</option>
                  <option value="pix">PIX</option>
                  <option value="credit">Crédito</option>
                  <option value="debit">Débito</option>
                </select>
                <p className="text-[11px] text-muted-foreground mt-1 leading-tight">
                  ⚠️ Importante: define como o dinheiro entrou. Se for <b>Dinheiro</b>,
                  o valor abatido da dívida soma no caixa em dinheiro.
                </p>
              </div>
              
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                  setShowAddCreditDialog(false);
                  setCreditCustomer(null);
                  setCreditAmount('');
                }}>
                  Cancelar
                </Button>
                <Button 
                  size="sm" 
                  className="flex-1 bg-green-600 hover:bg-green-700" 
                  onClick={handleConfirmAddCredit}
                  disabled={!creditAmount || parseFloat(creditAmount) <= 0}
                >
                  Adicionar Crédito
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* PIX Adjustment Dialog */}
      <Dialog open={showPixAdjustDialog} onOpenChange={setShowPixAdjustDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Smartphone className="h-4 w-4 text-blue-600" />
              Ajuste Manual de PIX
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-blue-50 rounded-lg p-3">
              <p className="text-sm text-muted-foreground">
                Adicione valores PIX recebidos fora de vendas (transferências diretas, pagamentos externos, etc.)
              </p>
            </div>
            
            <div>
              <Label className="text-sm">Valor (R$)</Label>
              <Input
                type="number"
                step="0.01"
                value={pixAdjustAmount}
                onChange={(e) => setPixAdjustAmount(e.target.value)}
                placeholder="0.00"
                className="h-10 text-lg"
                autoFocus
              />
            </div>
            
            <div>
              <Label className="text-sm">Descrição (opcional)</Label>
              <Input
                type="text"
                value={pixAdjustDescription}
                onChange={(e) => setPixAdjustDescription(e.target.value)}
                placeholder="Ex: Transferência cliente X"
                className="h-10"
              />
            </div>
            
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                setShowPixAdjustDialog(false);
                setPixAdjustAmount('');
                setPixAdjustDescription('');
              }}>
                Cancelar
              </Button>
              <Button 
                size="sm" 
                className="flex-1 bg-blue-600 hover:bg-blue-700" 
                onClick={handleAddPixAdjustment}
                disabled={!pixAdjustAmount || parseFloat(pixAdjustAmount) === 0}
              >
                Adicionar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Customer Dialog */}
      <Dialog open={showEditCustomerDialog} onOpenChange={setShowEditCustomerDialog}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Pencil className="h-4 w-4 text-blue-600" />
              Editar Cliente
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Nome do Cliente *</Label>
              <Input
                type="text"
                value={editCustomerData.name}
                onChange={(e) => setEditCustomerData({...editCustomerData, name: e.target.value})}
                placeholder="Nome completo"
                className="h-10"
                autoFocus
              />
            </div>
            
            <div>
              <Label className="text-sm">Telefone (WhatsApp)</Label>
              <Input
                type="tel"
                value={editCustomerData.phone}
                onChange={(e) => setEditCustomerData({...editCustomerData, phone: e.target.value})}
                placeholder="11999999999"
                className="h-10"
              />
            </div>
            
            <div>
              <Label className="text-sm">Observações</Label>
              <Input
                type="text"
                value={editCustomerData.notes}
                onChange={(e) => setEditCustomerData({...editCustomerData, notes: e.target.value})}
                placeholder="Observações sobre o cliente"
                className="h-10"
              />
            </div>
            
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                setShowEditCustomerDialog(false);
                setEditingCustomer(null);
              }}>
                Cancelar
              </Button>
              <Button 
                size="sm" 
                className="flex-1 bg-blue-600 hover:bg-blue-700" 
                onClick={handleSaveEditCustomer}
                disabled={!editCustomerData.name}
              >
                Salvar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Abater (Partial Payment) Dialog */}
      <Dialog open={showAbaterDialog} onOpenChange={(open) => {
        setShowAbaterDialog(open);
        if (!open) {
          setAbaterCustomer(null);
          setAbaterAmount('');
          setAbaterPassword('');
          setAbaterPaymentMethod('cash');
        }
      }}>
        <DialogContent className="max-w-[90vw] sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <Minus className="h-4 w-4 text-amber-600" />
              Pagamento Parcial (Abater)
            </DialogTitle>
          </DialogHeader>
          {abaterCustomer && (() => {
            const customerCredit = (prazoCustomers.find(
              c => c.name.toLowerCase() === abaterCustomer.name.toLowerCase()
            )?.credit) || 0;
            return (
            <div className="space-y-4">
              <div className="bg-amber-50 rounded-lg p-3">
                <p className="font-medium">{abaterCustomer.name}</p>
                <p className="text-xs text-muted-foreground">{abaterCustomer.order_count} pedido(s) pendente(s)</p>
                <div className="mt-2 pt-2 border-t border-amber-200 grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-xs text-muted-foreground">Dívida atual</p>
                    <p className="text-xl font-bold text-amber-600">{formatCurrency(abaterCustomer.total)}</p>
                  </div>
                  {customerCredit > 0 && (
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">Saldo a favor</p>
                      <p className="text-xl font-bold text-green-600">{formatCurrency(customerCredit)}</p>
                    </div>
                  )}
                </div>
              </div>
              
              <div>
                <Label className="text-sm">Valor a abater (R$)</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  max={abaterCustomer.total}
                  value={abaterAmount}
                  onChange={(e) => setAbaterAmount(e.target.value)}
                  placeholder="0.00"
                  className="h-10 text-lg"
                  autoFocus
                  data-testid="abater-amount-input"
                />
                {abaterAmount && parseFloat(abaterAmount) > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Nova dívida: {formatCurrency(abaterCustomer.total - parseFloat(abaterAmount))}
                  </p>
                )}
              </div>
              
              <div>
                <Label className="text-sm">Forma de Pagamento</Label>
                <div className={`grid ${customerCredit > 0 ? 'grid-cols-5' : 'grid-cols-4'} gap-1 mt-1`}>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={abaterPaymentMethod === 'cash' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${abaterPaymentMethod === 'cash' ? 'bg-amber-600' : ''}`}
                    onClick={() => setAbaterPaymentMethod('cash')}
                  >
                    <Banknote className="h-3 w-3 mr-1" /> Din
                  </Button>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={abaterPaymentMethod === 'pix' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${abaterPaymentMethod === 'pix' ? 'bg-amber-600' : ''}`}
                    onClick={() => setAbaterPaymentMethod('pix')}
                  >
                    <Smartphone className="h-3 w-3 mr-1" /> PIX
                  </Button>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={abaterPaymentMethod === 'debit' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${abaterPaymentMethod === 'debit' ? 'bg-amber-600' : ''}`}
                    onClick={() => setAbaterPaymentMethod('debit')}
                  >
                    <CreditCard className="h-3 w-3 mr-1" /> Débito
                  </Button>
                  <Button 
                    type="button" 
                    size="sm" 
                    variant={abaterPaymentMethod === 'credit' ? 'default' : 'outline'}
                    className={`h-9 text-xs ${abaterPaymentMethod === 'credit' ? 'bg-amber-600' : ''}`}
                    onClick={() => setAbaterPaymentMethod('credit')}
                  >
                    <CreditCard className="h-3 w-3 mr-1" /> Crédito
                  </Button>
                  {customerCredit > 0 && (
                    <Button 
                      type="button" 
                      size="sm" 
                      variant={abaterPaymentMethod === 'saldo' ? 'default' : 'outline'}
                      className={`h-9 text-xs ${abaterPaymentMethod === 'saldo' ? 'bg-green-600 hover:bg-green-700 text-white' : 'border-green-600 text-green-700'}`}
                      onClick={() => setAbaterPaymentMethod('saldo')}
                      data-testid="abater-saldo-btn"
                      title={`Usar saldo a favor (${formatCurrency(customerCredit)})`}
                    >
                      <DollarSign className="h-3 w-3 mr-1" /> Saldo
                    </Button>
                  )}
                </div>
                {abaterPaymentMethod === 'saldo' && (
                  <p className="text-xs text-green-700 mt-1">
                    Usando saldo a favor — dívida e saldo serão reduzidos em {formatCurrency(parseFloat(abaterAmount) || 0)}
                  </p>
                )}
              </div>
              
              <div>
                <Label className="text-sm">Senha de confirmação</Label>
                <Input
                  type="password"
                  value={abaterPassword}
                  onChange={(e) => setAbaterPassword(e.target.value)}
                  placeholder="Senha (1234)"
                  className="h-10"
                  data-testid="abater-password-input"
                />
              </div>
              
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => {
                  setShowAbaterDialog(false);
                  setAbaterCustomer(null);
                  setAbaterAmount('');
                  setAbaterPassword('');
                  setAbaterPaymentMethod('cash');
                }}>
                  Cancelar
                </Button>
                <Button 
                  size="sm" 
                  className="flex-1 bg-amber-600 hover:bg-amber-700" 
                  onClick={handleConfirmAbater}
                  disabled={!abaterAmount || parseFloat(abaterAmount) <= 0 || !abaterPassword}
                  data-testid="abater-confirm-btn"
                >
                  Confirmar Pagamento
                </Button>
              </div>
            </div>
            );
          })()}
        </DialogContent>
      </Dialog>

      {/* BIG new-order alert — modal fullscreen bloqueante com alarme sonoro em loop */}
      {newOrderAlert?.open && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 animate-in fade-in duration-300"
          data-testid="new-order-alert"
          role="alertdialog"
          aria-live="assertive"
        >
          <div
            className="max-w-2xl w-full rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300"
            style={{
              background: 'linear-gradient(135deg,#059669 0%,#10b981 60%,#34d399 100%)',
              animation: 'ganoh-pulse 1s ease-in-out infinite',
            }}
          >
            <style>{`
              @keyframes ganoh-pulse {
                0%, 100% { box-shadow: 0 0 0 0 rgba(16,185,129,0.7); }
                50%      { box-shadow: 0 0 0 22px rgba(16,185,129,0); }
              }
            `}</style>
            <div className="px-8 pt-8 pb-4 text-white">
              <div className="flex items-center gap-4 mb-4">
                <div className="text-6xl">🔔</div>
                <div>
                  <h2 className="text-3xl font-black tracking-tight">Novo pedido!</h2>
                  <p className="text-white/85 text-sm">{store === 'runner' ? 'Runner' : 'GYM Londres'} · agora mesmo</p>
                </div>
              </div>
              <div className="bg-white/15 backdrop-blur rounded-2xl p-4 space-y-2 max-h-[45vh] overflow-y-auto">
                {(newOrderAlert.orders || []).map((o, idx) => (
                  <div key={o.id || idx} className="bg-white/95 text-gray-900 rounded-xl px-4 py-3">
                    <div className="flex items-center justify-between mb-1">
                      <p className="font-bold text-lg truncate">#{o.order_number || (idx + 1)} — {o.customer_name || 'Sem nome'}</p>
                      <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 rounded px-2 py-0.5">
                        {o.pickup_time === 'manha' ? 'MANHÃ' : o.pickup_time === 'tarde' ? 'TARDE' : (o.pickup_time || 'AGORA').toUpperCase()}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 truncate">
                      {(o.items || []).slice(0, 3).map((i) => `${i.quantity || 1}× ${i.name}`).join(' · ')}
                      {(o.items || []).length > 3 ? ` +${o.items.length - 3}` : ''}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      R$ {Number(o.total || 0).toFixed(2)} · {String(o.payment_method || '').toUpperCase()}
                    </p>
                  </div>
                ))}
              </div>
            </div>
            <div className="px-8 pb-8 pt-2 flex flex-col sm:flex-row gap-3">
              <Button
                className="flex-1 h-14 text-lg font-bold bg-white text-emerald-700 hover:bg-emerald-50 active:scale-95 transition-transform"
                onClick={() => {
                  stopAlarmLoop();
                  setNewOrderAlert(null);
                  // Scroll to top so operator sees the fresh orders list
                  try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (_e) { /* ignore */ }
                }}
                data-testid="new-order-alert-view"
              >
                👀 Ver Pedidos
              </Button>
              <Button
                variant="ghost"
                className="h-14 text-white hover:bg-white/10 border border-white/30 active:scale-95 transition-transform"
                onClick={() => { stopAlarmLoop(); setNewOrderAlert(null); }}
                data-testid="new-order-alert-close"
              >
                Silenciar
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
