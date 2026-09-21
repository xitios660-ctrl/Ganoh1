import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { ScrollArea } from '../components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
  BarChart3, TrendingUp, TrendingDown, ShoppingBag, DollarSign,
  AlertTriangle, RefreshCw, LogOut, Home, Store,
  ChevronRight, Trash2, Plus, Pencil, UtensilsCrossed, CalendarClock, UserPlus, Receipt, Camera, Upload, Loader2, MessageCircle, QrCode, Users, PlusCircle
} from 'lucide-react';
import { Toaster, toast } from 'sonner';
import { AdicionaisTab, WhatsAppTab, PrazoTab } from '../components/gestor';
import { ThemeToggle } from '../components/ThemeToggle';
import '../styles/gestor-cinematic.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LOGO_URL = "/assets/ganoh-logo.png";

const formatPrice = (price) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(price || 0);

// Products List Dialog
const ProductsDialog = ({ isOpen, onClose, title, products, type }) => {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {type === 'top' ? <TrendingUp className="h-5 w-5 text-brand-600" /> : <TrendingDown className="h-5 w-5 text-red-500" />}
            {title}
          </DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="space-y-2 pr-4">
            {products.map((product, idx) => (
              <div 
                key={idx} 
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  type === 'top' ? 'bg-brand-50/50 border-brand-100' : 'bg-red-50/50 border-red-100'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                    type === 'top' ? 'bg-brand-600 text-white' : 'bg-red-500 text-white'
                  }`}>
                    {idx + 1}
                  </span>
                  <div>
                    <p className="font-medium text-sm">{product.name}</p>
                    <p className="text-xs text-muted-foreground">{product.count} vendidos</p>
                  </div>
                </div>
              </div>
            ))}
            {products.length === 0 && (
              <p className="text-center text-muted-foreground py-8">Sem dados disponíveis</p>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
};

export const GestorPage = () => {
  const navigate = useNavigate();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [productsDialog, setProductsDialog] = useState({ open: false, title: '', products: [], type: 'top' });
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [clearPassword, setClearPassword] = useState('');
  const [clickCount, setClickCount] = useState(0);
  const [isClearing, setIsClearing] = useState(false);
  const [chartData, setChartData] = useState(null);
  const [menuItems, setMenuItems] = useState([]);
  const [menuCategories, setMenuCategories] = useState([]);
  const [showMenuDialog, setShowMenuDialog] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [newItem, setNewItem] = useState({ name: '', description: '', price: '', category: '', store: 'runner', image_url: '' });
  const [activeMainTab, setActiveMainTab] = useState('dashboard');
  const [prazoCustomers, setPrazoCustomers] = useState([]);
  const [prazoDebts, setPrazoDebts] = useState({ debts: [], total_prazo: 0 });
  const [showPrazoDialog, setShowPrazoDialog] = useState(false);
  const [newPrazoCustomer, setNewPrazoCustomer] = useState({ name: '', phone: '', notes: '', store: 'runner' });
  
  // Chart view mode
  const [chartViewMode, setChartViewMode] = useState('month'); // 'month' or 'group'
  const [chartPeriod, setChartPeriod] = useState('day'); // 'day', 'month', 'year'
  const [chartSelectedDate, setChartSelectedDate] = useState(new Date());
  const [chartSelectedMonth, setChartSelectedMonth] = useState(new Date().getMonth() + 1);
  const [chartSelectedYear, setChartSelectedYear] = useState(new Date().getFullYear());
  const [chartStoreFilter, setChartStoreFilter] = useState('all'); // 'all', 'runner', 'gym-londres'
  const [salesByCategory, setSalesByCategory] = useState(null);
  
  // Expenses (Gastos) state
  const [expenses, setExpenses] = useState([]);
  const [expensesChartData, setExpensesChartData] = useState(null);
  const [showExpenseDialog, setShowExpenseDialog] = useState(false);
  // Manual sale state (Lançamento Manual de Vendas)
  const [showManualSaleDialog, setShowManualSaleDialog] = useState(false);
  const [newManualSale, setNewManualSale] = useState({ store: 'runner', payment_method: 'credit', amount: '', period: 'manha', description: '', date: '' });
  const [manualSales, setManualSales] = useState([]);
  const [savingManualSale, setSavingManualSale] = useState(false);
  const [newExpense, setNewExpense] = useState({ description: '', amount: '', category: 'outros', store: 'all', notes: '' });
  const [expenseImage, setExpenseImage] = useState(null);
  const [expenseImagePreview, setExpenseImagePreview] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzedExpense, setAnalyzedExpense] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const EXPENSE_CATEGORIES = ['contador', 'fornecedor', 'mercado', 'salgados', 'suplementos', 'VT', 'Vivo', 'sistema', 'salário', 'outros'];
  
  // Expenses chart period filters
  const [expensesPeriod, setExpensesPeriod] = useState('month');
  const [expensesSelectedMonth, setExpensesSelectedMonth] = useState(new Date().getMonth() + 1);
  const [expensesSelectedYear, setExpensesSelectedYear] = useState(new Date().getFullYear());
  const [expensesSelectedDate, setExpensesSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [expenseStoreFilter, setExpenseStoreFilter] = useState('all');
  // Contador export modal
  const [showContadorModal, setShowContadorModal] = useState(false);
  const [contadorEmail, setContadorEmail] = useState('');
  const [contadorExportData, setContadorExportData] = useState(null);
  const [isExportingContador, setIsExportingContador] = useState(false);
  
  // AI Chat for expenses
  const [showExpenseChat, setShowExpenseChat] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [pendingExpenseData, setPendingExpenseData] = useState(null);
  const [pendingExpensesList, setPendingExpensesList] = useState([]);
  const [awaitingCategory, setAwaitingCategory] = useState(false);
  const [expenseImages, setExpenseImages] = useState([]);
  
  // WhatsApp Bot states
  const [whatsappStatus, setWhatsappStatus] = useState('disconnected');
  const [whatsappQR, setWhatsappQR] = useState(null);
  const [whatsappSendingEnabled, setWhatsappSendingEnabled] = useState(false);
  const [whatsappGroups, setWhatsappGroups] = useState([]);
  const [whatsappTarget, setWhatsappTarget] = useState('');
  const [whatsappTargetInput, setWhatsappTargetInput] = useState('');
  
  // Adicionais states
  const [adicionais, setAdicionais] = useState([]);
  const [showAdicionalDialog, setShowAdicionalDialog] = useState(false);
  const [newAdicional, setNewAdicional] = useState({ name: '', price: '' });
  const [editingAdicional, setEditingAdicional] = useState(null);

  // Refetch chart when store filter changes (for ALL periods - day/week/month/year)
  useEffect(() => {
    if (isAuthenticated) {
      fetchChartData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartStoreFilter]);

  // Refetch expenses/Gastos KPIs when the Gastos store filter changes
  useEffect(() => {
    if (isAuthenticated) {
      fetchExpenses();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expenseStoreFilter]);

  // Auto-authenticate from localStorage on mount.
  // AuthPage stores credentials in localStorage.gestor_auth after a successful
  // tenant login, so the user shouldn't have to type the password a second time
  // when redirected to /gestor/dashboard.
  useEffect(() => {
    if (isAuthenticated) return;
    const stored = localStorage.getItem('gestor_auth');
    if (!stored) return;
    let user, pass;
    try {
      [user, pass] = atob(stored).split(':');
    } catch (_e) {
      localStorage.removeItem('gestor_auth');
      return;
    }
    if (!user || !pass) return;
    let active = true;
    (async () => {
      try {
        const response = await axios.get(`${API}/gestor/dashboard`, {
          auth: { username: user, password: pass }
        });
        if (!active) return;
        setUsername(user);
        setPassword(pass);
        setDashboard(response.data);
        setIsAuthenticated(true);
        // Schedule secondary fetches after auth state propagates
        setTimeout(() => {
          fetchChartData();
          fetchMenuItems();
          fetchPrazoData();
          fetchExpenses();
          fetchManualSales();
        }, 50);
      } catch (_e) {
        // Stale credentials — clear and let the manual login form show.
        localStorage.removeItem('gestor_auth');
        localStorage.removeItem('tenant_id');
        localStorage.removeItem('tenant_username');
      }
    })();
    return () => { active = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    // Trim whitespace to prevent mobile keyboard issues (auto-space, etc)
    const cleanUsername = (username || '').trim();
    const cleanPassword = (password || '').trim();
    try {
      const response = await axios.get(`${API}/gestor/dashboard`, {
        auth: { username: cleanUsername, password: cleanPassword }
      });
      setDashboard(response.data);
      setIsAuthenticated(true);
      localStorage.setItem('gestor_auth', btoa(`${cleanUsername}:${cleanPassword}`));
      
      // Fetch chart, menu, and prazo data after successful login
      setTimeout(() => {
        fetchChartData();
        fetchMenuItems();
        fetchPrazoData();
        fetchExpenses();
        fetchManualSales();
      }, 500);
    } catch (error) {
      toast.error('Credenciais inválidas');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchDashboard = async (showToast = false) => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    try {
      const [user, pass] = atob(auth).split(':');
      const response = await axios.get(`${API}/gestor/dashboard`, {
        auth: { username: user, password: pass }
      });
      setDashboard(response.data);
      if (showToast) toast.success('Dados atualizados');
    } catch (error) {
      localStorage.removeItem('gestor_auth');
      setIsAuthenticated(false);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Format Date to YYYY-MM-DD using LOCAL timezone (toISOString gives UTC,
  // which shifted the day by 3 hours for Brazil users near midnight).
  const toLocalDateStr = (d) => {
    if (typeof d === 'string') return d;
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  };

  const fetchChartData = async (period = chartPeriod, date = chartSelectedDate, month = chartSelectedMonth, year = chartSelectedYear) => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;

    try {
      const [user, pass] = atob(auth).split(':');

      let endpoint = `${API}/gestor/chart/monthly`;
      let params = {};
      const storeParam = chartStoreFilter !== 'all' ? chartStoreFilter : null;

      if (period === 'day') {
        params = { date: toLocalDateStr(date), store: storeParam };
        endpoint = `${API}/gestor/chart/daily`;
      } else if (period === 'week') {
        params = { date: toLocalDateStr(date), store: storeParam };
        endpoint = `${API}/gestor/chart/weekly`;
      } else if (period === 'month') {
        params = { month, year, store: storeParam };
        endpoint = `${API}/gestor/chart/monthly`;
      } else if (period === 'year') {
        params = { year, store: storeParam };
        endpoint = `${API}/gestor/chart/yearly`;
      }

      const response = await axios.get(endpoint, {
        auth: { username: user, password: pass },
        params
      });
      setChartData(response.data);
    } catch (error) {
      console.log('Error fetching chart data');
    }
  };

  const fetchSalesByCategory = async () => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    try {
      const [user, pass] = atob(auth).split(':');
      const response = await axios.get(`${API}/gestor/sales-by-category`, {
        auth: { username: user, password: pass }
      });
      setSalesByCategory(response.data);
    } catch (error) {
      console.log('Error fetching sales by category');
    }
  };

  const fetchMenuItems = async (store = 'runner') => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    try {
      const [user, pass] = atob(auth).split(':');
      const response = await axios.get(`${API}/gestor/menu/${store}`, {
        auth: { username: user, password: pass }
      });
      setMenuItems(response.data.menu);
      // Also fetch categories
      const catResponse = await axios.get(`${API}/categories`);
      setMenuCategories(catResponse.data.categories || []);
    } catch (error) {
      console.log('Error fetching menu');
    }
  };

  const handleSaveMenuItem = async () => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    const [user, pass] = atob(auth).split(':');
    const targetStore = newItem.store || selectedStore || 'runner';
    
    try {
      if (editingItem) {
        await axios.put(`${API}/gestor/menu/${editingItem.id}`, {
          name: newItem.name,
          description: newItem.description,
          price: parseFloat(newItem.price),
          category: newItem.category,
          image_url: newItem.image_url
        }, { auth: { username: user, password: pass } });
        toast.success('Item atualizado!');
      } else {
        await axios.post(`${API}/gestor/menu`, {
          ...newItem,
          price: parseFloat(newItem.price)
        }, { auth: { username: user, password: pass } });
        toast.success('Item adicionado ao cardápio!');
      }
      setShowMenuDialog(false);
      setEditingItem(null);
      setNewItem({ name: '', description: '', price: '', category: menuCategories[0] || '', store: 'runner', image_url: '' });
      // Refresh the menu of the store the item was added/edited to
      fetchMenuItems(targetStore);
    } catch (error) {
      const msg = error?.response?.data?.detail || 'Erro ao salvar item';
      toast.error(typeof msg === 'string' ? msg : 'Erro ao salvar item');
    }
  };

  const handleDeleteMenuItem = async (itemId) => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    const [user, pass] = atob(auth).split(':');
    
    try {
      await axios.delete(`${API}/gestor/menu/${itemId}`, {
        auth: { username: user, password: pass }
      });
      toast.success('Item removido!');
      fetchMenuItems(newItem.store);
    } catch (error) {
      toast.error('Erro ao remover item');
    }
  };

  const fetchPrazoData = async () => {
    try {
      const [customersRes, debtsRes] = await Promise.all([
        axios.get(`${API}/prazo/customers`),
        axios.get(`${API}/prazo/debts`)
      ]);
      setPrazoCustomers(customersRes.data.customers || []);
      setPrazoDebts(debtsRes.data);
    } catch (error) {
      console.log('Error fetching prazo data');
    }
  };

  const handleAddPrazoCustomer = async () => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth || !newPrazoCustomer.name) return;
    
    const [user, pass] = atob(auth).split(':');
    
    try {
      await axios.post(`${API}/prazo/customers`, newPrazoCustomer, {
        auth: { username: user, password: pass }
      });
      toast.success('Cliente cadastrado!');
      setShowPrazoDialog(false);
      setNewPrazoCustomer({ name: '', phone: '', notes: '', store: 'runner' });
      fetchPrazoData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao cadastrar');
    }
  };

  const handleDeletePrazoCustomer = async (customerId) => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    const [user, pass] = atob(auth).split(':');
    
    try {
      await axios.delete(`${API}/prazo/customers/${customerId}`, {
        auth: { username: user, password: pass }
      });
      toast.success('Cliente removido!');
      fetchPrazoData();
    } catch (error) {
      toast.error('Erro ao remover');
    }
  };

  // ==================== EXPENSES (GASTOS) FUNCTIONS ====================
  const fetchExpenses = async (period = expensesPeriod, date = expensesSelectedDate, month = expensesSelectedMonth, year = expensesSelectedYear, storeFilter = expenseStoreFilter) => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    const [user, pass] = atob(auth).split(':');
    
    try {
      let chartEndpoint = `${API}/gestor/chart/monthly-with-expenses`;
      let params = {};
      
      if (period === 'day') {
        params = { date };
        chartEndpoint = `${API}/gestor/chart/daily-with-expenses`;
      } else if (period === 'month') {
        params = { month, year };
        chartEndpoint = `${API}/gestor/chart/monthly-with-expenses`;
      } else if (period === 'year') {
        params = { year };
        chartEndpoint = `${API}/gestor/chart/yearly-with-expenses`;
      }

      // Send the store filter so backend computes Receita/Gastos/Lucro per loja
      if (storeFilter && storeFilter !== 'all') {
        params.store = storeFilter;
      }
      
      const [expensesRes, chartRes] = await Promise.all([
        axios.get(`${API}/expenses`, { auth: { username: user, password: pass } }),
        axios.get(chartEndpoint, { auth: { username: user, password: pass }, params })
      ]);
      setExpenses(expensesRes.data.expenses || []);
      setExpensesChartData(chartRes.data);
    } catch (error) {
      console.log('Error fetching expenses');
    }
  };

  const whatsappAuthConfig = () => {
    const value = localStorage.getItem('gestor_auth');
    return { headers: value ? { Authorization: `Basic ${value}` } : {}, timeout: 15000 };
  };

  const connectWhatsApp = async () => {
    try {
      await axios.post(`${API}/whatsapp/connect`, {}, whatsappAuthConfig());
      await fetchWhatsAppStatus();
    } catch (error) {
      toast.error('Não foi possível iniciar a conexão. Confira o serviço do WhatsApp.');
    }
  };

  const fetchWhatsAppStatus = async () => {
    try {
      const response = await axios.get(`${API}/whatsapp/status`, whatsappAuthConfig());
      setWhatsappStatus(response.data.status);
      setWhatsappSendingEnabled(response.data.sendingEnabled === true);
      
      // If not connected, fetch QR code
      if (response.data.status !== 'connected' && response.data.status !== 'offline') {
        try {
          const qrResponse = await axios.get(`${API}/whatsapp/qr`, whatsappAuthConfig());
          setWhatsappQR(qrResponse.data.qrCode);
        } catch (e) {
          console.log('Could not fetch QR code');
        }
      } else {
        setWhatsappQR(null);
      }
      
      // Fetch groups if connected
      if (response.data.status === 'connected') {
        try {
          const groupsResponse = await axios.get(`${API}/whatsapp/groups`, whatsappAuthConfig());
          setWhatsappGroups(groupsResponse.data.groups || []);
          setWhatsappTarget(groupsResponse.data.currentTarget || '');
        } catch (e) {
          console.log('Could not fetch groups');
        }
      }
    } catch (error) {
      setWhatsappStatus('offline');
      setWhatsappQR(null);
    }
  };

  const saveWhatsAppTarget = async () => {
    try {
      await axios.post(`${API}/whatsapp/set-target`, { target: whatsappTargetInput }, whatsappAuthConfig());
      setWhatsappTarget(whatsappTargetInput);
      toast.success('Destino das notificações atualizado!');
    } catch (error) {
      toast.error('Erro ao salvar destino');
    }
  };

  const joinWhatsAppGroup = async () => {
    if (!whatsappTargetInput.includes('chat.whatsapp.com')) {
      toast.error('Cole um link de grupo válido (chat.whatsapp.com/...)');
      return;
    }
    try {
      toast.loading('Entrando no grupo...', { id: 'join-group' });
      const response = await axios.post(`${API}/whatsapp/join-group`, { inviteLink: whatsappTargetInput }, whatsappAuthConfig());
      if (response.data.success) {
        toast.success('Entrou no grupo com sucesso!', { id: 'join-group' });
        setWhatsappTarget(response.data.groupId);
        fetchWhatsAppStatus();
      } else {
        toast.error(response.data.error || 'Erro ao entrar no grupo', { id: 'join-group' });
      }
    } catch (error) {
      toast.error('Erro ao entrar no grupo', { id: 'join-group' });
    }
  };

  // ==================== ADICIONAIS FUNCTIONS ====================
  const fetchAdicionais = async () => {
    try {
      const response = await axios.get(`${API}/gestor/adicionais`, {
        auth: { username, password }
      });
      setAdicionais(response.data.adicionais || []);
    } catch (error) {
      console.log('Erro ao carregar adicionais');
    }
  };

  const handleSaveAdicional = async () => {
    if (!newAdicional.name || !newAdicional.price) {
      toast.error('Preencha nome e preço');
      return;
    }
    try {
      if (editingAdicional) {
        await axios.put(`${API}/gestor/adicionais/${editingAdicional.id}`, {
          name: newAdicional.name,
          price: parseFloat(newAdicional.price)
        }, { auth: { username, password } });
        toast.success('Adicional atualizado!');
      } else {
        await axios.post(`${API}/gestor/adicionais`, {
          name: newAdicional.name,
          price: parseFloat(newAdicional.price)
        }, { auth: { username, password } });
        toast.success('Adicional criado!');
      }
      setShowAdicionalDialog(false);
      setNewAdicional({ name: '', price: '' });
      setEditingAdicional(null);
      fetchAdicionais();
    } catch (error) {
      toast.error('Erro ao salvar adicional');
    }
  };

  const handleDeleteAdicional = async (adicionalId) => {
    try {
      await axios.delete(`${API}/gestor/adicionais/${adicionalId}`, {
        auth: { username, password }
      });
      toast.success('Adicional removido!');
      fetchAdicionais();
    } catch (error) {
      toast.error('Erro ao remover adicional');
    }
  };

  const openEditAdicional = (adicional) => {
    setEditingAdicional(adicional);
    setNewAdicional({ name: adicional.name, price: adicional.price.toString() });
    setShowAdicionalDialog(true);
  };

  useEffect(() => {
    if (activeMainTab === 'adicionais' && isAuthenticated) {
      fetchAdicionais();
    }
  }, [activeMainTab, isAuthenticated]);

  // Poll WhatsApp status every 5 seconds when on WhatsApp tab
  useEffect(() => {
    if (activeMainTab === 'whatsapp' && isAuthenticated) {
      fetchWhatsAppStatus();
      const interval = setInterval(fetchWhatsAppStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [activeMainTab, isAuthenticated]);

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
        
        const base64 = canvas.toDataURL('image/jpeg', quality);
        resolve(base64);
      };
      
      img.src = URL.createObjectURL(file);
    });
  };

  const handleExpenseImageChange = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;
    
    // Filter files by size
    const validFiles = files.filter(f => f.size <= 10 * 1024 * 1024);
    if (validFiles.length < files.length) {
      toast.error(`${files.length - validFiles.length} imagem(ns) muito grande(s). Máximo 10MB.`);
    }
    
    if (validFiles.length === 0) return;
    
    toast.loading(`Processando ${validFiles.length} imagem(ns)...`, { id: 'compress' });
    
    try {
      const compressedImages = await Promise.all(
        validFiles.map(file => compressImage(file))
      );
      
      // Store all images
      setExpenseImages(compressedImages);
      setExpenseImagePreview(compressedImages[0]); // Show first as preview
      toast.dismiss('compress');
      
      // Auto-start AI analysis with multiple images
      startExpenseChatWithMultipleImages(compressedImages);
    } catch (error) {
      toast.error('Erro ao processar imagens', { id: 'compress' });
    }
  };

  // Parse ALL expense commands from input like "O de 6 é mercado o de 22 é suplemento o de 35 é sistema"
  const parseAllExpenseCommands = (input) => {
    const commands = [];
    const normalized = input.toLowerCase();
    
    // Global regex to find all patterns like "o de X é categoria" or "X é categoria" or "X categoria"
    // Matches: "o de 6 é mercado", "6 é mercado", "6 mercado", "35 fornecedor"
    const globalPattern = /(?:o\s+de\s+)?(\d+(?:[.,]\d+)?)\s*(?:reais?|r\$)?\s*(?:é|e|=|:)?\s*(\w+)/gi;
    
    let match;
    while ((match = globalPattern.exec(normalized)) !== null) {
      const amount = parseFloat(match[1].replace(',', '.'));
      const categoryWord = match[2];
      const category = matchCategory(categoryWord);
      
      if (category && amount && !isNaN(amount)) {
        // Avoid duplicates
        if (!commands.find(c => c.amount === amount && c.category === category)) {
          commands.push({ amount, category });
        }
      }
    }
    
    return commands;
  };

  // Parse single expense command (legacy support)
  const parseExpenseCommand = (input) => {
    const commands = parseAllExpenseCommands(input);
    return commands.length > 0 ? commands[0] : null;
  };

  // Smart category matching - understands variations
  const matchCategory = (input) => {
    const normalized = input.toLowerCase().trim();
    
    // Direct match
    const directMatch = EXPENSE_CATEGORIES.find(cat => 
      cat.toLowerCase() === normalized
    );
    if (directMatch) return directMatch;
    
    // Category aliases and variations
    const categoryAliases = {
      'contador': ['contador', 'contabilidade', 'contábil', 'conta'],
      'fornecedor': ['fornecedor', 'fornecedores', 'distribuidora', 'distribuidor', 'atacado'],
      'mercado': ['mercado', 'supermercado', 'compras', 'feira', 'hortifruti', 'mercearia', 'compra mercado', 'compras mercado', 'super'],
      'suplementos': ['suplementos', 'suplemento', 'whey', 'creatina', 'proteina', 'vitamina', 'nutricao'],
      'VT': ['vt', 'vale transporte', 'transporte', 'passagem', 'bilhete', 'vale-transporte'],
      'Vivo': ['vivo', 'telefone', 'celular', 'internet', 'plano', 'operadora', 'tim', 'claro', 'oi'],
      'sistema': ['sistema', 'software', 'programa', 'app', 'aplicativo', 'assinatura', 'mensalidade', 'licença'],
      'salário': ['salario', 'salário', 'funcionario', 'funcionário', 'pagamento', 'folha', 'empregado', 'colaborador'],
      'outros': ['outros', 'outro', 'diversos', 'geral', 'variados']
    };
    
    // Check aliases
    for (const [category, aliases] of Object.entries(categoryAliases)) {
      for (const alias of aliases) {
        if (normalized.includes(alias) || alias.includes(normalized)) {
          return category;
        }
      }
    }
    
    // Fuzzy match - check if any word matches
    const words = normalized.split(/\s+/);
    for (const word of words) {
      if (word.length < 3) continue;
      for (const [category, aliases] of Object.entries(categoryAliases)) {
        for (const alias of aliases) {
          if (alias.includes(word) || word.includes(alias.substring(0, 4))) {
            return category;
          }
        }
      }
    }
    
    return null;
  };

  // AI Chat functions for expense analysis
  const startExpenseChatWithImage = async (imageData) => {
    startExpenseChatWithMultipleImages([imageData]);
  };

  const startExpenseChatWithMultipleImages = async (imagesData) => {
    setShowExpenseChat(true);
    setChatMessages([{ role: 'system', content: `🔍 Analisando ${imagesData.length} imagem(ns)... Você pode ir digitando as categorias enquanto isso!` }]);
    setIsAnalyzing(true);
    setPendingExpensesList([]);
    
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    const [user, pass] = atob(auth).split(':');
    
    // Save current input to process after analysis
    const preTypedInput = chatInput;
    
    try {
      const base64Images = imagesData.map(img => img.split(',')[1] || img);
      
      const response = await axios.post(`${API}/expenses/analyze-multiple`, {
        images: base64Images
      }, { auth: { username: user, password: pass } });
      
      if (response.data.success && response.data.expenses?.length > 0) {
        const expenses = response.data.expenses;
        setPendingExpensesList(expenses);
        
        // Create list message
        let listMessage = `📋 **Encontrei ${expenses.length} gasto(s):**\n\n`;
        expenses.forEach((exp, idx) => {
          const storeLabel = exp.store === 'runner' ? '🏃 Runner' : 
                            exp.store === 'gym-londres' ? '🏋️ GYM' : '📦 Geral';
          listMessage += `**${idx + 1}.** R$ ${exp.amount?.toFixed(2) || '0.00'} - ${exp.description || 'Sem descrição'} [${storeLabel}]\n`;
          if (exp.notes) listMessage += `   📍 ${exp.notes}\n`;
          listMessage += '\n';
        });
        
        listMessage += `**Categorize:** Ex: "35 fornecedor, 22 mercado, 6 suplemento"`;
        
        setChatMessages([{ role: 'assistant', content: listMessage }]);
        setAwaitingCategory(true);
        
        // If user pre-typed something, process it automatically
        if (preTypedInput && preTypedInput.trim()) {
          // Small delay to update state first
          setTimeout(() => {
            processPreTypedInput(preTypedInput, expenses, user, pass);
          }, 100);
        }
      } else {
        setChatMessages([
          { role: 'assistant', content: '❌ Não consegui ler as imagens. Tente fotos mais claras.' }
        ]);
      }
    } catch (error) {
      setChatMessages([
        { role: 'assistant', content: `❌ Erro ao analisar: ${error.response?.data?.detail || 'Tente novamente'}` }
      ]);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Process pre-typed input after analysis completes
  const processPreTypedInput = async (input, expenses, user, pass) => {
    if (!input.trim() || expenses.length === 0) return;
    
    setChatMessages(prev => [...prev, { role: 'user', content: input }]);
    setChatInput('');
    
    // Parse all commands using global regex
    const allCommands = parseAllExpenseCommands(input);
    
    if (allCommands.length > 0) {
      const savedExpenses = [];
      let remainingExpenses = [...expenses];
      
      for (const cmd of allCommands) {
        const matchingExpense = remainingExpenses.find(exp => 
          Math.abs(exp.amount - cmd.amount) < 1
        );
        
        if (matchingExpense) {
          try {
            await axios.post(`${API}/expenses`, {
              description: matchingExpense.description,
              amount: matchingExpense.amount,
              category: cmd.category,
              store: matchingExpense.store || 'all',
              notes: matchingExpense.notes || '',
              image_url: ''
            }, { auth: { username: user, password: pass } });
            
            savedExpenses.push({ ...matchingExpense, category: cmd.category });
            remainingExpenses = remainingExpenses.filter(e => e !== matchingExpense);
          } catch (error) {
            console.error('Error saving expense:', error);
          }
        }
      }
      
      if (savedExpenses.length > 0) {
        setPendingExpensesList(remainingExpenses);
        
        let response = `✅ **${savedExpenses.length} gasto(s) salvo(s):**\n`;
        savedExpenses.forEach(exp => {
          response += `• R$ ${exp.amount?.toFixed(2)} → **${exp.category}**\n`;
        });
        
        if (remainingExpenses.length > 0) {
          response += `\n📋 Faltam ${remainingExpenses.length}:\n`;
          remainingExpenses.forEach((exp, idx) => {
            response += `${idx + 1}. R$ ${exp.amount?.toFixed(2)} - ${exp.description}\n`;
          });
        } else {
          response += '\n✅ Todos salvos!';
          setAwaitingCategory(false);
          fetchExpenses();
          setTimeout(() => closeExpenseChat(), 2000);
        }
        
        setChatMessages(prev => [...prev, { role: 'assistant', content: response }]);
        toast.success(`${savedExpenses.length} gastos salvos!`);
      }
    }
  };

  const startExpenseChat = async () => {
    if (expenseImages.length === 0 && !expenseImage) {
      toast.error('Selecione uma imagem primeiro');
      return;
    }
    if (expenseImages.length > 0) {
      startExpenseChatWithMultipleImages(expenseImages);
    } else {
      startExpenseChatWithImage(expenseImage);
    }
  };

  const handleChatSubmit = async () => {
    if (!chatInput.trim() || !awaitingCategory) return;
    
    const userMessage = chatInput.trim();
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setChatInput('');
    
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    const [user, pass] = atob(auth).split(':');
    
    // Parse ALL expense commands from the message using global regex
    const allCommands = parseAllExpenseCommands(userMessage);
    
    // If we found commands, process them all at once
    if (allCommands.length > 0 && pendingExpensesList.length > 0) {
      const savedExpenses = [];
      let remainingExpenses = [...pendingExpensesList];
      
      for (const cmd of allCommands) {
        // Find expense by amount (with tolerance of 1 real)
        const matchingExpense = remainingExpenses.find(exp => 
          Math.abs(exp.amount - cmd.amount) < 1
        );
        
        if (matchingExpense) {
          try {
            await axios.post(`${API}/expenses`, {
              description: matchingExpense.description,
              amount: matchingExpense.amount,
              category: cmd.category,
              store: matchingExpense.store || 'all',
              notes: matchingExpense.notes || '',
              image_url: ''
            }, { auth: { username: user, password: pass } });
            
            savedExpenses.push({ ...matchingExpense, category: cmd.category });
            remainingExpenses = remainingExpenses.filter(e => e !== matchingExpense);
          } catch (error) {
            console.error('Error saving expense:', error);
          }
        }
      }
      
      if (savedExpenses.length > 0) {
        setPendingExpensesList(remainingExpenses);
        
        let response = `✅ **${savedExpenses.length} gasto(s) salvo(s):**\n`;
        savedExpenses.forEach(exp => {
          response += `• R$ ${exp.amount?.toFixed(2)} → **${exp.category}**\n`;
        });
        
        if (remainingExpenses.length > 0) {
          response += `\n📋 Faltam ${remainingExpenses.length}:\n`;
          remainingExpenses.forEach((exp, idx) => {
            response += `${idx + 1}. R$ ${exp.amount?.toFixed(2)} - ${exp.description}\n`;
          });
        } else {
          response += '\n✅ Todos salvos!';
          setAwaitingCategory(false);
          fetchExpenses();
          setTimeout(() => closeExpenseChat(), 2000);
        }
        
        setChatMessages(prev => [...prev, { role: 'assistant', content: response }]);
        toast.success(`${savedExpenses.length} gastos salvos!`);
        return;
      }
    }
    
    // If no specific commands found, try to apply category to ALL pending
    const validCategory = matchCategory(userMessage);
    
    if (validCategory && pendingExpensesList.length > 0) {
      try {
        for (const exp of pendingExpensesList) {
          await axios.post(`${API}/expenses`, {
            description: exp.description,
            amount: exp.amount,
            category: validCategory,
            store: exp.store || 'all',
            notes: exp.notes || '',
            image_url: ''
          }, { auth: { username: user, password: pass } });
        }
        
        const total = pendingExpensesList.reduce((sum, e) => sum + (e.amount || 0), 0);
        
        setChatMessages(prev => [...prev, { 
          role: 'assistant', 
          content: `✅ **${pendingExpensesList.length} gasto(s) salvos!**\n\n💰 Total: R$ ${total.toFixed(2)}\n🏷️ Categoria: **${validCategory}**` 
        }]);
        
        setPendingExpensesList([]);
        setAwaitingCategory(false);
        fetchExpenses();
        toast.success(`${pendingExpensesList.length} gastos salvos!`);
        
        setTimeout(() => closeExpenseChat(), 2000);
      } catch (error) {
        setChatMessages(prev => [...prev, { role: 'assistant', content: '❌ Erro ao salvar.' }]);
      }
    } else {
      setChatMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `🤔 Não entendi.\n\nExemplos:\n• "6 mercado 22 suplemento 35 sistema"\n• "mercado" (aplica a todos)` 
      }]);
    }
  };

  const closeExpenseChat = () => {
    setShowExpenseChat(false);
    setChatMessages([]);
    setPendingExpenseData(null);
    setPendingExpensesList([]);
    setAwaitingCategory(false);
    setExpenseImage(null);
    setExpenseImages([]);
    setExpenseImagePreview(null);
  };

  const handleAnalyzeExpense = async () => {
    // Legacy function - now redirects to chat
    startExpenseChat();
  };

  const handleSaveExpense = async () => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth || !newExpense.description || !newExpense.amount) return;
    
    const [user, pass] = atob(auth).split(':');
    
    try {
      await axios.post(`${API}/expenses`, {
        ...newExpense,
        amount: parseFloat(newExpense.amount),
        image_url: expenseImagePreview || ''
      }, { auth: { username: user, password: pass } });
      
      toast.success('Gasto registrado!');
      setShowExpenseDialog(false);
      setNewExpense({ description: '', amount: '', category: 'outros', store: 'all', notes: '' });
      setExpenseImage(null);
      setExpenseImagePreview(null);
      setAnalyzedExpense(null);
      fetchExpenses();
      fetchChartData();
    } catch (error) {
      toast.error('Erro ao salvar gasto');
    }
  };

  // ============== MANUAL SALES (lançamento manual de vendas) ==============
  const fetchManualSales = async () => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    const [user, pass] = atob(auth).split(':');
    try {
      const res = await axios.get(`${API}/gestor/manual-sales`, { auth: { username: user, password: pass }, params: { limit: 50 } });
      setManualSales(res.data.sales || []);
    } catch (e) { /* silent */ }
  };

  const handleSaveManualSale = async () => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    const [user, pass] = atob(auth).split(':');
    const amountStr = String(newManualSale.amount).replace(',', '.').trim();
    const amountNum = parseFloat(amountStr);
    if (!amountNum || amountNum <= 0) {
      toast.error('Informe um valor maior que zero');
      return;
    }
    setSavingManualSale(true);
    try {
      const body = {
        store: newManualSale.store,
        payment_method: newManualSale.payment_method,
        amount: amountNum,
        period: newManualSale.period,
        description: newManualSale.description || '',
      };
      if (newManualSale.date) body.date = newManualSale.date;
      await axios.post(`${API}/gestor/manual-sale`, body, { auth: { username: user, password: pass } });
      toast.success(`Venda manual lançada: R$ ${amountNum.toFixed(2)}`);
      setShowManualSaleDialog(false);
      setNewManualSale({ store: 'runner', payment_method: 'credit', amount: '', period: 'manha', description: '', date: '' });
      fetchManualSales();
      fetchExpenses();
      fetchChartData();
    } catch (error) {
      const msg = error?.response?.data?.detail || 'Erro ao lançar venda manual';
      toast.error(typeof msg === 'string' ? msg : 'Erro ao lançar venda manual');
    } finally {
      setSavingManualSale(false);
    }
  };

  const handleDeleteManualSale = async (orderId) => {
    if (!window.confirm('Excluir esta venda manual? Os KPIs voltarão a não contabilizar este valor.')) return;
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    const [user, pass] = atob(auth).split(':');
    try {
      await axios.delete(`${API}/gestor/manual-sale/${orderId}`, { auth: { username: user, password: pass } });
      toast.success('Venda manual removida');
      fetchManualSales();
      fetchExpenses();
      fetchChartData();
    } catch (error) {
      toast.error('Erro ao remover venda manual');
    }
  };

  const handleDeleteExpense = async (expenseId) => {
    const auth = localStorage.getItem('gestor_auth');
    if (!auth) return;
    
    const [user, pass] = atob(auth).split(':');
    
    try {
      await axios.delete(`${API}/expenses/${expenseId}`, {
        auth: { username: user, password: pass }
      });
      toast.success('Gasto removido!');
      fetchExpenses();
      fetchChartData();
    } catch (error) {
      toast.error('Erro ao remover gasto');
    }
  };

  const handleExportContador = async () => {
    try {
      const auth = localStorage.getItem('gestor_auth');
      if (!auth) {
        toast.error('Não autenticado');
        return;
      }
      const [user, pass] = atob(auth).split(':');
      
      setIsExportingContador(true);
      toast.loading('Buscando dados...', { id: 'export' });
      
      const response = await axios.get(`${API}/expenses/export-contador`, {
        params: {
          month: expensesSelectedMonth,
          year: expensesSelectedYear,
          store: expenseStoreFilter !== 'all' ? expenseStoreFilter : null
        },
        auth: { username: user, password: pass }
      });
      
      setContadorExportData(response.data);
      setShowContadorModal(true);
      toast.dismiss('export');
    } catch (error) {
      console.error('Export error:', error);
      toast.error('Erro ao buscar dados', { id: 'export' });
    } finally {
      setIsExportingContador(false);
    }
  };

  const handleDownloadContadorReport = () => {
    if (!contadorExportData) return;
    
    const blob = new Blob([JSON.stringify(contadorExportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `relatorio_contador_${contadorExportData.periodo.mes_nome}_${contadorExportData.periodo.ano}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success('Relatório baixado!');
  };

  const handleSendContadorEmail = async () => {
    if (!contadorEmail) {
      toast.error('Digite o e-mail do contador');
      return;
    }
    
    try {
      const auth = localStorage.getItem('gestor_auth');
      if (!auth) {
        toast.error('Não autenticado');
        return;
      }
      const [user, pass] = atob(auth).split(':');
      
      toast.loading('Enviando relatório por e-mail...', { id: 'email' });
      
      const response = await axios.post(`${API}/expenses/send-contador-email`, {
        email: contadorEmail,
        month: expensesSelectedMonth,
        year: expensesSelectedYear,
        store: expenseStoreFilter !== 'all' ? expenseStoreFilter : null
      }, {
        auth: { username: user, password: pass }
      });
      
      if (response.data.success) {
        toast.success(`Relatório enviado para ${contadorEmail}!`, { id: 'email' });
        setContadorEmail('');
      } else {
        toast.error('Erro ao enviar e-mail', { id: 'email' });
      }
    } catch (error) {
      console.error('Email error:', error);
      const errorMsg = error.response?.data?.detail || 'Erro ao enviar e-mail';
      toast.error(errorMsg, { id: 'email' });
    }
  };

  useEffect(() => {
    // Check for tenant auth first
    const tenantId = localStorage.getItem('tenant_id');
    const auth = localStorage.getItem('gestor_auth');
    
    if (!tenantId && !auth) {
      // Redirect to auth page if not logged in
      navigate('/auth');
      return;
    }
    
    if (auth) {
      setIsAuthenticated(true);
      fetchDashboard();
      fetchChartData();
      fetchMenuItems();
      fetchPrazoData();
      fetchExpenses();
    }
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('gestor_auth');
    localStorage.removeItem('tenant_id');
    localStorage.removeItem('tenant_username');
    localStorage.removeItem('tenant_display_name');
    setIsAuthenticated(false);
    setDashboard(null);
    navigate('/auth');
  };

  const openProductsDialog = (title, products, type) => {
    setProductsDialog({ open: true, title, products, type });
  };

  // Hidden clear button - requires 5 clicks on logo + password
  const handleLogoClick = () => {
    const newCount = clickCount + 1;
    setClickCount(newCount);
    if (newCount >= 5) {
      setShowClearDialog(true);
      setClickCount(0);
    }
    // Reset after 3 seconds
    setTimeout(() => setClickCount(0), 3000);
  };

  const handleClearData = async () => {
    setIsClearing(true);
    try {
      await axios.post(`${API}/admin/clear-data?password=${clearPassword}`);
      toast.success('Todos os dados foram apagados!');
      setShowClearDialog(false);
      setClearPassword('');
      fetchDashboard(true);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Senha incorreta');
    } finally {
      setIsClearing(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-brand-50 to-background flex items-center justify-center p-4">
        <Toaster position="top-center" richColors />
        <div className="w-full max-w-sm">
          <div className="text-center mb-6">
            <img src={LOGO_URL} alt="GANOH" className="h-16 mx-auto mb-4" />
            <h1 className="font-heading text-2xl font-bold">Painel do Gestor</h1>
            <p className="text-sm text-muted-foreground">Acesso restrito</p>
          </div>
          
          <form onSubmit={handleLogin} className="bg-white rounded-xl shadow-lg p-6 space-y-4">
            <Input type="text" placeholder="Usuário" value={username} onChange={(e) => setUsername(e.target.value)} required data-testid="gestor-username" />
            <Input type="password" placeholder="Senha" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="gestor-password" />
            <Button type="submit" className="w-full bg-brand-600 hover:bg-brand-700" disabled={isLoading}>
              {isLoading ? 'Entrando...' : 'Entrar'}
            </Button>
          </form>
          
          <div className="mt-4 text-center">
            <Button variant="ghost" onClick={() => navigate('/')}>
              <Home className="h-4 w-4 mr-2" /> Voltar
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="gx-app min-h-screen" data-testid="gestor-page">
      <span className="gx-orb gx-orb-1" />
      <span className="gx-orb gx-orb-2" />
      <span className="gx-orb gx-orb-3" />
      <Toaster position="top-center" richColors theme="dark" />
      
      {/* Header */}
      <header className="gx-header sticky top-0 z-50">
        <div className="gx-header-inner max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="gx-logo-wrap" onClick={handleLogoClick} data-testid="gestor-logo">
              <img src={LOGO_URL} alt="GANOH" className="gx-logo-img select-none" />
            </div>
            <div>
              <h1 className="gx-brand-title">GANOH <span style={{ fontStyle: 'italic', fontWeight: 400 }}>· Painel</span></h1>
              <p className="gx-brand-sub">Cinematic Edition · MMXXVI</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <button className="gx-icon-btn" onClick={() => { setIsRefreshing(true); fetchDashboard(true); }} disabled={isRefreshing} title="Atualizar" data-testid="gestor-refresh-btn">
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            </button>
            <button className="gx-icon-btn" onClick={handleLogout} title="Sair" data-testid="gestor-logout-btn">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="gx-main max-w-7xl mx-auto px-4 py-6 relative" style={{ zIndex: 5 }}>
        {/* Main Navigation Tabs */}
        <Tabs value={activeMainTab} onValueChange={setActiveMainTab} className="space-y-4">
          <TabsList className="gx-nav grid w-full grid-cols-6 mb-4" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--gx-line)' }}>
            <TabsTrigger value="dashboard" className="flex items-center gap-1 text-xs gx-nav-btn data-[state=active]:gx-active">
              <BarChart3 className="h-3 w-3" /> Dashboard
            </TabsTrigger>
            <TabsTrigger value="chart" className="flex items-center gap-1 text-xs gx-nav-btn data-[state=active]:gx-active">
              <TrendingUp className="h-3 w-3" /> Gráfico
            </TabsTrigger>
            <TabsTrigger value="gastos" className="flex items-center gap-1 text-xs gx-nav-btn data-[state=active]:gx-active">
              <Receipt className="h-3 w-3" /> Gastos
            </TabsTrigger>
            <TabsTrigger value="prazo" className="flex items-center gap-1 text-xs gx-nav-btn data-[state=active]:gx-active">
              <CalendarClock className="h-3 w-3" /> Prazo
            </TabsTrigger>
            <TabsTrigger value="menu" className="flex items-center gap-1 text-xs gx-nav-btn data-[state=active]:gx-active" data-testid="gestor-tab-menu">
              <UtensilsCrossed className="h-3 w-3" /> Cardápio
            </TabsTrigger>
            <TabsTrigger value="whatsapp" className="flex items-center gap-1 text-xs gx-nav-btn data-[state=active]:gx-active">
              <MessageCircle className="h-3 w-3" /> WhatsApp
            </TabsTrigger>
          </TabsList>

          {/* DASHBOARD TAB */}
          <TabsContent value="dashboard">
        {dashboard && (
          <>
            {/* Combined Stats — KPI 3D glass cards */}
            <div className="gx-kpi-grid mb-6">
              <div className="gx-kpi gx-enter" data-i="1" data-testid="kpi-receita-hoje">
                <div className="gx-kpi-label">
                  <span className="gx-kpi-icon"><DollarSign className="h-4 w-4" /></span> Receita Hoje
                </div>
                <div className="gx-kpi-value green gx-counter">{formatPrice(dashboard.combined.today_total)}</div>
                <div className="gx-kpi-foot">{dashboard.combined.today_orders} pedido(s)</div>
              </div>
              <div className="gx-kpi gx-enter" data-i="2" data-testid="kpi-receita-mes">
                <div className="gx-kpi-label">
                  <span className="gx-kpi-icon cyan"><TrendingUp className="h-4 w-4" /></span> Receita Mês
                </div>
                <div className="gx-kpi-value cyan gx-counter">{formatPrice(dashboard.combined.month_total)}</div>
                <div className="gx-kpi-foot">{dashboard.combined.month_orders} no mês</div>
              </div>
              <div className="gx-kpi gx-enter" data-i="3" data-testid="kpi-pedidos-hoje">
                <div className="gx-kpi-label">
                  <span className="gx-kpi-icon violet"><ShoppingBag className="h-4 w-4" /></span> Pedidos Hoje
                </div>
                <div className="gx-kpi-value gx-counter">{dashboard.combined.today_orders}</div>
                <div className="gx-kpi-foot">Atualizado agora</div>
              </div>
              <div className="gx-kpi gx-enter" data-i="4" data-testid="kpi-pedidos-mes">
                <div className="gx-kpi-label">
                  <span className="gx-kpi-icon amber"><BarChart3 className="h-4 w-4" /></span> Pedidos Mês
                </div>
                <div className="gx-kpi-value amber gx-counter">{dashboard.combined.month_orders}</div>
                <div className="gx-kpi-foot">Soma das duas lojas</div>
              </div>
            </div>

            {/* Store Tabs */}
            <Tabs defaultValue="runner" className="space-y-4">
              <TabsList className="gx-nav grid w-full grid-cols-2" style={{ background: 'rgba(168,217,107,0.04)' }}>
                <TabsTrigger value="runner" className="flex items-center gap-2 gx-nav-btn data-[state=active]:gx-active">
                  <Store className="h-4 w-4" /> Runner
                </TabsTrigger>
                <TabsTrigger value="gym-londres" className="flex items-center gap-2 gx-nav-btn data-[state=active]:gx-active">
                  <Store className="h-4 w-4" /> GYM Londres
                </TabsTrigger>
              </TabsList>

              {Object.entries(dashboard.stores).map(([storeKey, storeData]) => (
                <TabsContent key={storeKey} value={storeKey} className="space-y-4">
                  {/* Live Dashboard Link */}
                  <a
                    href={`/${storeKey}/live`}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid={`live-dashboard-link-${storeKey}`}
                    className="gx-live-banner"
                  >
                    <div className="flex items-center gap-3">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#a8d96b] opacity-60" />
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-[#a8d96b]" />
                      </span>
                      <div>
                        <p className="gx-live-title">Painel ao Vivo · {storeKey === 'runner' ? 'Runner' : 'GYM Londres'}</p>
                        <p className="gx-live-sub">Abrir tela cinematográfica para TV da loja</p>
                      </div>
                    </div>
                    <span className="text-xs font-medium" style={{ color: 'var(--gx-green)' }}>Abrir →</span>
                  </a>

                  {/* Store Stats — dark cards */}
                  <div className="gx-kpi-grid">
                    <div className="gx-kpi gx-enter" data-i="1">
                      <div className="gx-kpi-label"><span className="gx-kpi-icon"><DollarSign className="h-4 w-4" /></span> Receita Hoje</div>
                      <div className="gx-kpi-value green">{formatPrice(storeData.today.total)}</div>
                      <div className="gx-kpi-foot">{storeData.today.order_count} pedidos</div>
                    </div>
                    <div className="gx-kpi gx-enter" data-i="2">
                      <div className="gx-kpi-label"><span className="gx-kpi-icon cyan"><TrendingUp className="h-4 w-4" /></span> Receita Mês</div>
                      <div className="gx-kpi-value cyan">{formatPrice(storeData.month.total)}</div>
                      <div className="gx-kpi-foot">{storeData.month.order_count} pedidos</div>
                    </div>
                    {storeData.low_stock_alerts > 0 && (
                      <div className="gx-kpi gx-enter md:col-span-2" data-i="3" style={{ borderColor: 'rgba(251,113,133,0.3)' }}>
                        <div className="gx-kpi-label"><span className="gx-kpi-icon rose"><AlertTriangle className="h-4 w-4" /></span> Estoque baixo</div>
                        <div className="gx-kpi-value rose">{storeData.low_stock_alerts}</div>
                        <button
                          className="gx-btn-ghost mt-2"
                          onClick={() => navigate(`/${storeKey}/cozinha`)}
                          style={{ fontSize: 11 }}
                        >
                          Ver na cozinha →
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Top and Low Products — dark glass cards */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div
                      className="gx-card cursor-pointer transition-transform hover:-translate-y-0.5"
                      onClick={() => openProductsDialog(`Mais Vendidos · ${storeData.name}`, storeData.top_products, 'top')}
                      data-testid={`top-products-${storeKey}`}
                    >
                      <div className="gx-card-head">
                        <div className="gx-card-title">
                          <TrendingUp className="h-4 w-4" style={{ color: 'var(--gx-green)' }} />
                          Mais Vendidos (Mês)
                        </div>
                        <ChevronRight className="h-4 w-4" style={{ color: 'var(--gx-mute)' }} />
                      </div>
                      <div className="gx-card-body">
                        <div className="space-y-2">
                          {storeData.top_products.slice(0, 3).map((product, idx) => (
                            <div key={idx} className="flex justify-between items-center text-sm py-1.5 border-b last:border-0" style={{ borderColor: 'var(--gx-line)' }}>
                              <div className="flex items-center gap-2">
                                <span className="w-5 h-5 rounded-full grid place-items-center text-xs font-bold" style={{ background: 'linear-gradient(135deg,var(--gx-green),var(--gx-green-2))', color: '#0a1503' }}>{idx + 1}</span>
                                <span className="font-medium truncate max-w-[160px]" style={{ color: 'var(--gx-ink)' }}>{product.name}</span>
                              </div>
                              <span className="font-semibold" style={{ color: 'var(--gx-green)' }}>{product.count}x</span>
                            </div>
                          ))}
                          {storeData.top_products.length === 0 && (
                            <p className="text-sm text-center py-2" style={{ color: 'var(--gx-mute)' }}>Sem dados</p>
                          )}
                          {storeData.top_products.length > 3 && (
                            <p className="text-xs text-center pt-2" style={{ color: 'var(--gx-green)' }}>Ver todos ({storeData.top_products.length})</p>
                          )}
                        </div>
                      </div>
                    </div>

                    <div
                      className="gx-card cursor-pointer transition-transform hover:-translate-y-0.5"
                      onClick={() => openProductsDialog(`Menos Vendidos · ${storeData.name}`, storeData.low_products, 'low')}
                      data-testid={`low-products-${storeKey}`}
                    >
                      <div className="gx-card-head">
                        <div className="gx-card-title">
                          <TrendingDown className="h-4 w-4" style={{ color: 'var(--gx-rose)' }} />
                          Menos Vendidos (Mês)
                        </div>
                        <ChevronRight className="h-4 w-4" style={{ color: 'var(--gx-mute)' }} />
                      </div>
                      <div className="gx-card-body">
                        <div className="space-y-2">
                          {storeData.low_products.slice(0, 3).map((product, idx) => (
                            <div key={idx} className="flex justify-between items-center text-sm py-1.5 border-b last:border-0" style={{ borderColor: 'var(--gx-line)' }}>
                              <span className="font-medium truncate max-w-[180px]" style={{ color: 'var(--gx-ink)' }}>{product.name}</span>
                              <span className="font-semibold" style={{ color: 'var(--gx-rose)' }}>{product.count}x</span>
                            </div>
                          ))}
                          {storeData.low_products.length === 0 && (
                            <p className="text-sm text-center py-2" style={{ color: 'var(--gx-mute)' }}>Sem dados</p>
                          )}
                          {storeData.low_products.length > 3 && (
                            <p className="text-xs text-center pt-2" style={{ color: 'var(--gx-rose)' }}>Ver todos ({storeData.low_products.length})</p>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Quick Actions */}
                  <div className="flex gap-2">
                    <button className="gx-btn-ghost" onClick={() => navigate(`/${storeKey}/cozinha`)} data-testid={`open-kitchen-${storeKey}`}>
                      Ver Cozinha →
                    </button>
                  </div>
                </TabsContent>
              ))}
            </Tabs>
          </>
        )}
          </TabsContent>

          {/* CHART TAB — Cinematic */}
          <TabsContent value="chart">
            <div className="gx-card">
              <div className="gx-card-head">
                <div className="gx-card-title">
                  <TrendingUp className="h-5 w-5" style={{ color: 'var(--gx-green)' }} />
                  {chartPeriod === 'day' ? 'Vendas do Dia' :
                   chartPeriod === 'week' ? 'Vendas da Semana' :
                   chartPeriod === 'month' ? 'Vendas do Mês' :
                   'Vendas do Ano'}
                </div>
                <div className="gx-seg">
                  <button className={`gx-seg-btn ${chartPeriod === 'day' ? 'active' : ''}`} onClick={() => { setChartPeriod('day'); fetchChartData('day'); }} data-testid="chart-period-day">Dia</button>
                  <button className={`gx-seg-btn ${chartPeriod === 'week' ? 'active' : ''}`} onClick={() => { setChartPeriod('week'); fetchChartData('week'); }} data-testid="chart-period-week">Semana</button>
                  <button className={`gx-seg-btn ${chartPeriod === 'month' ? 'active' : ''}`} onClick={() => { setChartPeriod('month'); fetchChartData('month'); }} data-testid="chart-period-month">Mês</button>
                  <button className={`gx-seg-btn ${chartPeriod === 'year' ? 'active' : ''}`} onClick={() => { setChartPeriod('year'); fetchChartData('year'); }} data-testid="chart-period-year">Ano</button>
                </div>
              </div>
              <div className="gx-card-body">
                {/* Period Selectors */}
                <div className="flex gap-2 mb-4 flex-wrap items-center">
                  {(chartPeriod === 'day' || chartPeriod === 'week') && (
                    <>
                      <Input
                        type="date"
                        value={chartSelectedDate instanceof Date ? chartSelectedDate.toISOString().split('T')[0] : chartSelectedDate}
                        onChange={(e) => {
                          setChartSelectedDate(e.target.value);
                          fetchChartData(chartPeriod, e.target.value);
                        }}
                        className="w-auto gx-input"
                        style={{ width: 180 }}
                        data-testid="chart-date-input"
                      />
                      <Select
                        value={chartStoreFilter}
                        onValueChange={setChartStoreFilter}
                      >
                        <SelectTrigger className="w-36" data-testid="chart-store-filter">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Todas Lojas</SelectItem>
                          <SelectItem value="runner">🏃 Runner</SelectItem>
                          <SelectItem value="gym-londres">🏋️ GYM Londres</SelectItem>
                        </SelectContent>
                      </Select>
                    </>
                  )}
                  {chartPeriod === 'month' && (
                    <>
                      <Select
                        value={chartSelectedMonth.toString()}
                        onValueChange={(v) => {
                          const m = parseInt(v);
                          setChartSelectedMonth(m);
                          fetchChartData('month', null, m, chartSelectedYear);
                        }}
                      >
                        <SelectTrigger className="w-32" data-testid="chart-month-select">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'].map((m, i) => (
                            <SelectItem key={i+1} value={(i+1).toString()}>{m}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select
                        value={chartSelectedYear.toString()}
                        onValueChange={(v) => {
                          const y = parseInt(v);
                          setChartSelectedYear(y);
                          fetchChartData('month', null, chartSelectedMonth, y);
                        }}
                      >
                        <SelectTrigger className="w-24" data-testid="chart-year-select-month">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[2024, 2025, 2026].map(y => (
                            <SelectItem key={y} value={y.toString()}>{y}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </>
                  )}
                  {chartPeriod === 'year' && (
                    <Select
                      value={chartSelectedYear.toString()}
                      onValueChange={(v) => {
                        const y = parseInt(v);
                        setChartSelectedYear(y);
                        fetchChartData('year', null, null, y);
                      }}
                    >
                      <SelectTrigger className="w-24" data-testid="chart-year-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {[2024, 2025, 2026].map(y => (
                          <SelectItem key={y} value={y.toString()}>{y}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                {chartData ? (
                  <>
                    <div className="flex justify-between items-center mb-4">
                      <span className="text-sm" style={{ color: 'var(--gx-mute)' }}>
                        {chartPeriod === 'day' ? chartData.date :
                         chartPeriod === 'week' ? `${chartData.start} → ${chartData.end}` :
                         chartPeriod === 'month' ? chartData.month :
                         `Ano ${chartData.year}`}
                      </span>
                      <span className="text-2xl font-bold gx-counter" style={{ color: 'var(--gx-green)', fontFamily: 'Playfair Display, serif' }}>
                        {formatPrice(chartPeriod === 'day' ? chartData.total_day :
                                    chartPeriod === 'week' ? chartData.total_week :
                                    chartPeriod === 'month' ? chartData.total_month :
                                    chartData.total_year)}
                      </span>
                    </div>
                    {/* Bar Chart — cinematic */}
                    <div className="gx-chart-shell" style={{ height: 260 }}>
                      <div className="h-full flex items-end justify-between gap-1 relative">
                        {chartData.data.map((item, idx) => {
                          const values = chartData.data.map(d => d.total);
                          const maxValue = Math.max(...values, 1);
                          const heightPercent = item.total > 0 ? Math.max((item.total / maxValue) * 100, 5) : 2;
                          return (
                            <div
                              key={idx}
                              className="flex-1 min-w-[10px] max-w-[40px] flex flex-col items-center group relative h-full gx-bar-wrap"
                            >
                              <div className="flex-1 w-full flex items-end justify-center">
                                <div
                                  className={`w-full gx-bar ${item.total > 0 ? '' : 'zero'}`}
                                  style={{ height: `${heightPercent}%`, minHeight: item.total > 0 ? '8px' : '2px' }}
                                />
                              </div>
                              <div className="gx-tooltip">
                                {chartPeriod === 'day' ? item.hour :
                                 chartPeriod === 'week' ? item.label :
                                 chartPeriod === 'month' ? `Dia ${item.day}` :
                                 item.month_name}: <strong style={{ color: 'var(--gx-green)' }}>{formatPrice(item.total)}</strong>
                                <br/><span style={{ color: 'var(--gx-mute)' }}>{item.count} pedidos</span>
                              </div>
                              <span className="text-[9px] mt-1.5 shrink-0" style={{ color: 'var(--gx-mute)' }}>
                                {chartPeriod === 'day' ? item.hour?.slice(0,2) :
                                 chartPeriod === 'week' ? `${item.day_name?.slice(0,3)}` :
                                 chartPeriod === 'month' ? item.day :
                                 item.month_name?.slice(0,3)}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Summary stats — dark glass */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
                      <div className="gx-kpi" style={{ padding: '14px 16px' }}>
                        <div className="gx-kpi-label" style={{ fontSize: 9.5, letterSpacing: 2 }}>
                          <span className="gx-kpi-icon" style={{ height: 24, width: 24 }}><DollarSign className="h-3 w-3" /></span>
                          Total {chartPeriod === 'day' ? 'do Dia' : chartPeriod === 'week' ? 'da Semana' : chartPeriod === 'month' ? 'do Mês' : 'do Ano'}
                        </div>
                        <div className="gx-kpi-value green" style={{ marginTop: 8, fontSize: 22 }}>
                          {formatPrice(chartPeriod === 'day' ? chartData.total_day :
                                      chartPeriod === 'week' ? chartData.total_week :
                                      chartPeriod === 'month' ? chartData.total_month :
                                      chartData.total_year)}
                        </div>
                      </div>
                      <div className="gx-kpi" style={{ padding: '14px 16px' }}>
                        <div className="gx-kpi-label" style={{ fontSize: 9.5, letterSpacing: 2 }}>
                          <span className="gx-kpi-icon cyan" style={{ height: 24, width: 24 }}><ShoppingBag className="h-3 w-3" /></span>
                          Pedidos
                        </div>
                        <div className="gx-kpi-value cyan" style={{ marginTop: 8, fontSize: 22 }}>{chartData.total_orders}</div>
                      </div>
                      {chartData.by_store && (
                        <>
                          <div className="gx-kpi" style={{ padding: '14px 16px' }}>
                            <div className="gx-kpi-label" style={{ fontSize: 9.5, letterSpacing: 2 }}>
                              <span className="gx-kpi-icon violet" style={{ height: 24, width: 24 }}>🏃</span>
                              Runner
                            </div>
                            <div className="gx-kpi-value" style={{ marginTop: 8, fontSize: 18, color: 'var(--gx-violet)' }}>
                              {formatPrice(chartData.by_store.runner?.total || 0)}
                            </div>
                            <div className="gx-kpi-foot">{chartData.by_store.runner?.orders || 0} pedidos</div>
                          </div>
                          <div className="gx-kpi" style={{ padding: '14px 16px' }}>
                            <div className="gx-kpi-label" style={{ fontSize: 9.5, letterSpacing: 2 }}>
                              <span className="gx-kpi-icon amber" style={{ height: 24, width: 24 }}>🏋️</span>
                              GYM Londres
                            </div>
                            <div className="gx-kpi-value amber" style={{ marginTop: 8, fontSize: 18 }}>
                              {formatPrice(chartData.by_store.gym_londres?.total || 0)}
                            </div>
                            <div className="gx-kpi-foot">{chartData.by_store.gym_londres?.orders || 0} pedidos</div>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Receita por Forma de Pagamento */}
                    {chartData.by_payment && (
                      <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--gx-line)' }}>
                        <h4 className="text-sm font-semibold mb-3 text-center" style={{ color: 'var(--gx-ink-soft)', letterSpacing: 2, textTransform: 'uppercase', fontSize: 11 }}>
                          Receita por Forma de Pagamento
                        </h4>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
                          {[
                            { key: 'pix', label: 'PIX', color: 'green' },
                            { key: 'debito', label: 'Débito', color: 'cyan' },
                            { key: 'credito', label: 'Crédito', color: 'violet' },
                            { key: 'dinheiro', label: 'Dinheiro', color: 'emerald' },
                            { key: 'prazo', label: 'Prazo', color: 'amber' },
                            { key: 'voucher', label: 'Voucher', color: 'rose' },
                          ].map((m) => (
                            <div key={m.key} className="gx-row" style={{ flexDirection: 'column', alignItems: 'flex-start', padding: 10 }}>
                              <span className={`gx-pill ${m.color}`} style={{ fontSize: 10 }}>{m.label}</span>
                              <span className="text-sm font-bold gx-counter mt-1" style={{ color: 'var(--gx-ink)' }}>
                                {formatPrice(chartData.by_payment[m.key] || 0)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="gx-kpi-grid" data-testid="dashboard-skeleton" aria-label="Carregando dados">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="gx-kpi" style={{ minHeight: 110 }}>
                        <div className="gx-skeleton-line" style={{ width: '40%', height: 12, marginBottom: 12 }} />
                        <div className="gx-skeleton-line" style={{ width: '70%', height: 28, marginBottom: 10 }} />
                        <div className="gx-skeleton-line" style={{ width: '55%', height: 10 }} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </TabsContent>
          {/* GASTOS TAB */}
          <TabsContent value="gastos">
            <div className="space-y-4">
              {/* Header with Add Button */}
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Receipt className="h-5 w-5 text-red-600" />
                  Gestão de Gastos
                </h2>
                <div className="flex gap-2 flex-wrap">
                  <Button 
                    variant="outline"
                    onClick={handleExportContador}
                    title="Exportar para Contador"
                  >
                    <DollarSign className="h-4 w-4 mr-1" /> Exportar IR
                  </Button>
                  <Button
                    variant="outline"
                    className="border-emerald-400/40 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20"
                    onClick={() => {
                      setNewManualSale({ store: 'runner', payment_method: 'credit', amount: '', period: 'manha', description: '', date: '' });
                      setShowManualSaleDialog(true);
                    }}
                    data-testid="open-manual-sale-dialog"
                    title="Lançar venda manual (turno/total não digitado pedido a pedido)"
                  >
                    <DollarSign className="h-4 w-4 mr-1" /> + Venda Manual
                  </Button>
                  <Button 
                    className="bg-brand-600 hover:bg-brand-700"
                    onClick={() => {
                      setExpenseImage(null);
                      setExpenseImagePreview(null);
                      setChatMessages([]);
                      setAwaitingCategory(false);
                      setShowExpenseChat(true);
                    }}
                  >
                    <Camera className="h-4 w-4 mr-1" /> Foto + IA
                  </Button>
                  <Button 
                    variant="outline"
                    onClick={() => {
                      setShowExpenseDialog(true);
                      setAnalyzedExpense(null);
                      setExpenseImage(null);
                      setExpenseImagePreview(null);
                      setNewExpense({ description: '', amount: '', category: 'outros', store: 'all', notes: '' });
                    }}
                  >
                    <Plus className="h-4 w-4 mr-1" /> Manual
                  </Button>
                </div>
              </div>

              {/* Store Filter */}
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Filtrar por Loja:</span>
                <Select value={expenseStoreFilter} onValueChange={setExpenseStoreFilter}>
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="runner">Runner</SelectItem>
                    <SelectItem value="gym-londres">GYM Londres</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Summary Cards */}
              {expensesChartData && (
                <div className="gx-kpi-grid">
                  <div className="gx-kpi gx-enter" data-i="1" data-testid="gastos-revenue">
                    <div className="gx-kpi-label"><span className="gx-kpi-icon emerald"><TrendingUp className="h-4 w-4" /></span> Receita do Mês</div>
                    <div className="gx-kpi-value" style={{ color: 'var(--gx-emerald)' }}>{formatPrice(expensesChartData.total_revenue)}</div>
                  </div>
                  <div className="gx-kpi gx-enter" data-i="2" data-testid="gastos-expenses">
                    <div className="gx-kpi-label"><span className="gx-kpi-icon rose"><Receipt className="h-4 w-4" /></span> Gastos do Mês</div>
                    <div className="gx-kpi-value rose">{formatPrice(expensesChartData.total_expenses)}</div>
                  </div>
                  <div className="gx-kpi gx-enter" data-i="3" data-testid="gastos-profit">
                    <div className="gx-kpi-label">
                      <span className={`gx-kpi-icon ${expensesChartData.total_profit >= 0 ? '' : 'rose'}`}>
                        <DollarSign className="h-4 w-4" />
                      </span>
                      Lucro do Mês
                    </div>
                    <div className={`gx-kpi-value ${expensesChartData.total_profit >= 0 ? 'green' : 'rose'}`}>
                      {formatPrice(expensesChartData.total_profit)}
                    </div>
                  </div>
                  <div className="gx-kpi gx-enter" data-i="4" data-testid="gastos-orders">
                    <div className="gx-kpi-label"><span className="gx-kpi-icon cyan"><ShoppingBag className="h-4 w-4" /></span> Pedidos</div>
                    <div className="gx-kpi-value cyan">{expensesChartData.total_orders}</div>
                  </div>
                </div>
              )}

              {/* Category Filter Buttons */}
              <div className="flex flex-wrap gap-2">
                <Button 
                  variant={selectedCategory === 'all' ? 'default' : 'outline'} 
                  size="sm"
                  onClick={() => setSelectedCategory('all')}
                  className={selectedCategory === 'all' ? 'bg-brand-600' : ''}
                >
                  Todos
                </Button>
                {EXPENSE_CATEGORIES.map(cat => (
                  <Button 
                    key={cat}
                    variant={selectedCategory === cat ? 'default' : 'outline'} 
                    size="sm"
                    onClick={() => setSelectedCategory(cat)}
                    className={selectedCategory === cat ? 'bg-brand-600' : ''}
                  >
                    {cat} {expensesChartData?.expenses_by_category?.[cat] ? `(${formatPrice(expensesChartData.expenses_by_category[cat])})` : ''}
                  </Button>
                ))}
              </div>

              {/* Chart with Revenue vs Expenses */}
              {expensesChartData && (
                <div className="gx-card">
                  <div className="gx-card-head">
                    <div className="gx-card-title">
                      <BarChart3 className="h-5 w-5" style={{ color: 'var(--gx-green)' }} />
                      Receita vs Gastos
                    </div>
                    <div className="gx-seg">
                      <button className={`gx-seg-btn ${expensesPeriod === 'day' ? 'active' : ''}`} onClick={() => { setExpensesPeriod('day'); fetchExpenses('day'); }} data-testid="gastos-period-day">Dia</button>
                      <button className={`gx-seg-btn ${expensesPeriod === 'month' ? 'active' : ''}`} onClick={() => { setExpensesPeriod('month'); fetchExpenses('month'); }} data-testid="gastos-period-month">Mês</button>
                      <button className={`gx-seg-btn ${expensesPeriod === 'year' ? 'active' : ''}`} onClick={() => { setExpensesPeriod('year'); fetchExpenses('year'); }} data-testid="gastos-period-year">Ano</button>
                    </div>
                  </div>
                  <div className="gx-card-body">
                    {/* Period selectors */}
                    <div className="flex gap-2 mb-4 flex-wrap items-center">
                      {expensesPeriod === 'day' && (
                        <Input 
                          type="date" 
                          value={expensesSelectedDate}
                          onChange={(e) => {
                            setExpensesSelectedDate(e.target.value);
                            fetchExpenses('day', e.target.value);
                          }}
                          className="w-auto gx-input"
                          style={{ width: 180 }}
                        />
                      )}
                      {expensesPeriod === 'month' && (
                        <>
                          <Select 
                            value={expensesSelectedMonth.toString()} 
                            onValueChange={(v) => {
                              const m = parseInt(v);
                              setExpensesSelectedMonth(m);
                              fetchExpenses('month', null, m, expensesSelectedYear);
                            }}
                          >
                            <SelectTrigger className="w-32">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'].map((m, i) => (
                                <SelectItem key={i+1} value={(i+1).toString()}>{m}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Select 
                            value={expensesSelectedYear.toString()} 
                            onValueChange={(v) => {
                              const y = parseInt(v);
                              setExpensesSelectedYear(y);
                              fetchExpenses('month', null, expensesSelectedMonth, y);
                            }}
                          >
                            <SelectTrigger className="w-24">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {[2024, 2025, 2026].map(y => (
                                <SelectItem key={y} value={y.toString()}>{y}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </>
                      )}
                      {expensesPeriod === 'year' && (
                        <Select 
                          value={expensesSelectedYear.toString()} 
                          onValueChange={(v) => {
                            const y = parseInt(v);
                            setExpensesSelectedYear(y);
                            fetchExpenses('year', null, null, y);
                          }}
                        >
                          <SelectTrigger className="w-24">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {[2024, 2025, 2026].map(y => (
                              <SelectItem key={y} value={y.toString()}>{y}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                      <span className="text-sm ml-auto" style={{ color: 'var(--gx-mute)' }}>
                        {expensesPeriod === 'day' ? expensesChartData.date : 
                         expensesPeriod === 'month' ? expensesChartData.month : 
                         `Ano ${expensesChartData.year}`}
                      </span>
                    </div>
                    
                    <div className="gx-chart-shell" style={{ height: 220 }}>
                      <div className="h-full flex items-end justify-between gap-1">
                        {expensesChartData.data.map((item, idx) => {
                          const maxValue = Math.max(...expensesChartData.data.map(d => Math.max(d.revenue, d.expenses)), 1);
                          const revenueHeight = item.revenue > 0 ? Math.max((item.revenue / maxValue) * 100, 5) : 2;
                          const expenseHeight = item.expenses > 0 ? Math.max((item.expenses / maxValue) * 100, 5) : 2;
                          return (
                            <div 
                              key={idx} 
                              className="flex-1 min-w-[10px] max-w-[35px] flex flex-col items-center group relative h-full gx-bar-wrap"
                            >
                              <div className="flex-1 w-full flex items-end justify-center gap-[2px]">
                                <div 
                                  className={`w-1/2 gx-bar ${item.revenue > 0 ? '' : 'zero'}`}
                                  style={{ height: `${revenueHeight}%`, minHeight: item.revenue > 0 ? '6px' : '2px' }}
                                />
                                <div 
                                  className={`w-1/2 gx-bar-red ${item.expenses > 0 ? '' : 'zero'}`}
                                  style={{ height: `${expenseHeight}%`, minHeight: item.expenses > 0 ? '6px' : '2px' }}
                                />
                              </div>
                              <div className="gx-tooltip">
                                <strong>{expensesPeriod === 'day' ? item.hour : 
                                 expensesPeriod === 'month' ? `Dia ${item.day}` : 
                                 item.month_name}</strong><br/>
                                Receita: <span style={{ color: 'var(--gx-green)' }}>{formatPrice(item.revenue)}</span><br/>
                                Gastos: <span style={{ color: 'var(--gx-rose)' }}>{formatPrice(item.expenses)}</span><br/>
                                Lucro: <span style={{ color: item.profit >= 0 ? 'var(--gx-green)' : 'var(--gx-rose)' }}>{formatPrice(item.profit)}</span>
                              </div>
                              <span className="text-[9px] mt-1.5 shrink-0" style={{ color: 'var(--gx-mute)' }}>
                                {expensesPeriod === 'day' ? item.hour?.slice(0,2) : 
                                 expensesPeriod === 'month' ? item.day : 
                                 item.month_name}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="flex justify-center gap-4 mt-3 text-xs">
                      <div className="flex items-center gap-1" style={{ color: 'var(--gx-ink-soft)' }}>
                        <div className="w-3 h-3 rounded" style={{ background: 'linear-gradient(180deg, var(--gx-green), var(--gx-green-2))' }} />
                        <span>Receita</span>
                      </div>
                      <div className="flex items-center gap-1" style={{ color: 'var(--gx-ink-soft)' }}>
                        <div className="w-3 h-3 rounded" style={{ background: 'linear-gradient(180deg, #fb7185, #be123c)' }} />
                        <span>Gastos</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Expenses List */}
              <div className="gx-card">
                <div className="gx-card-head">
                  <div className="gx-card-title">
                    <Receipt className="h-5 w-5" style={{ color: 'var(--gx-green)' }} />
                    Lista de Gastos
                  </div>
                </div>
                <div className="gx-card-body">
                  {expenses.length > 0 ? (
                    <div className="space-y-2 max-h-96 overflow-y-auto gx-scroll">
                      {expenses
                        .filter(e => selectedCategory === 'all' || e.category?.toLowerCase() === selectedCategory.toLowerCase())
                        .filter(e => expenseStoreFilter === 'all' || e.store === expenseStoreFilter || e.store === 'all')
                        .map((expense) => (
                        <div key={expense.id} className="gx-row">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-medium" style={{ color: 'var(--gx-ink)' }}>{expense.description}</span>
                              <span className="gx-pill rose">{expense.category}</span>
                              {expense.store && expense.store !== 'all' && (
                                <span className="gx-pill cyan">
                                  {expense.store === 'runner' ? 'Runner' : 'GYM Londres'}
                                </span>
                              )}
                            </div>
                            <p className="text-xs mt-1" style={{ color: 'var(--gx-mute)' }}>
                              {new Date(expense.created_at).toLocaleDateString('pt-BR')} • {expense.notes || 'Sem observações'}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold" style={{ color: 'var(--gx-rose)' }}>{formatPrice(expense.amount)}</span>
                            <button
                              className="gx-icon-btn"
                              style={{ color: 'var(--gx-rose)', height: 32, width: 32 }}
                              onClick={() => handleDeleteExpense(expense.id)}
                              aria-label={`Excluir gasto: ${expense.description}`}
                              title="Excluir gasto"
                              data-testid={`delete-expense-${expense.id}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8" style={{ color: 'var(--gx-mute)' }}>
                      <Receipt className="h-10 w-10 mx-auto mb-2 opacity-30" />
                      <p>Nenhum gasto registrado</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </TabsContent>

          {/* PRAZO TAB - Cinematic */}
          <TabsContent value="prazo">
            <PrazoTab
              prazoCustomers={prazoCustomers}
              prazoDebts={prazoDebts}
              onOpenNewCustomer={() => setShowPrazoDialog(true)}
              onDeleteCustomer={handleDeletePrazoCustomer}
              onRefresh={fetchPrazoData}
            />
          </TabsContent>

          {/* MENU TAB */}
          <TabsContent value="menu">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <UtensilsCrossed className="h-5 w-5 text-brand-600" />
                    Gerenciar Cardápio
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        if (!window.confirm('Padronizar grafia de TODOS os produtos e adicionais? Esta ação corrige nomes (ex: "Yorgut" → "Iogurte", "Jun gle" → "Jungle") e remove duplicatas. Não pode ser desfeita.')) return;
                        try {
                          const auth = localStorage.getItem('gestor_auth');
                          const [user, pass] = atob(auth).split(':');
                          const res = await axios.post(`${API}/admin/fix-product-names`, {}, {
                            auth: { username: user, password: pass }
                          });
                          const t = res.data.totals;
                          toast.success(`Padronização concluída: ${t.products_renamed} renomeados, ${t.products_merged} duplicados removidos, ${t.adicionais_renamed} adicionais ajustados.`);
                          fetchMenuItems(newItem.store);
                        } catch (_e) {
                          toast.error('Erro ao padronizar nomes');
                        }
                      }}
                      data-testid="fix-product-names-btn"
                    >
                      Corrigir Grafia
                    </Button>
                    <Button
                      size="sm"
                      className="bg-brand-600 hover:bg-brand-700"
                      onClick={() => {
                        setEditingItem(null);
                        setNewItem({ name: '', description: '', price: '', category: 'Lanches', store: 'runner', image_url: '' });
                        setShowMenuDialog(true);
                      }}
                    >
                      <Plus className="h-4 w-4 mr-1" /> Adicionar Item
                    </Button>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {/* Store selector for menu */}
                <div className="mb-4">
                  <Select value={newItem.store} onValueChange={(v) => { setNewItem({...newItem, store: v}); fetchMenuItems(v); }}>
                    <SelectTrigger className="w-48">
                      <SelectValue placeholder="Selecione a loja" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="runner">Runner</SelectItem>
                      <SelectItem value="gym-londres">GYM Londres</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                {menuItems.length > 0 ? (
                  <div className="space-y-2">
                    {menuItems.map((item) => (
                      <div key={item.id} className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg border">
                        <div className="flex-1">
                          <p className="font-medium">{item.name}</p>
                          <p className="text-sm text-muted-foreground">{item.category} • {formatPrice(item.price)}</p>
                        </div>
                        <div className="flex gap-1">
                          <Button 
                            size="icon" 
                            variant="ghost"
                            onClick={() => {
                              setEditingItem(item);
                              setNewItem({
                                name: item.name,
                                description: item.description || '',
                                price: item.price.toString(),
                                category: item.category,
                                store: item.store,
                                image_url: item.image_url || ''
                              });
                              setShowMenuDialog(true);
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button 
                            size="icon" 
                            variant="ghost" 
                            className="text-red-600"
                            onClick={() => handleDeleteMenuItem(item.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <UtensilsCrossed className="h-10 w-10 mx-auto mb-2 opacity-30" />
                    <p>Nenhum item no cardápio</p>
                    <p className="text-sm">Clique em "Adicionar Item" para começar</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ADICIONAIS TAB */}
          <TabsContent value="adicionais">
            <AdicionaisTab 
              adicionais={adicionais}
              onNewAdicional={() => { setEditingAdicional(null); setNewAdicional({ name: '', price: '' }); setShowAdicionalDialog(true); }}
              onEditAdicional={openEditAdicional}
              onDeleteAdicional={handleDeleteAdicional}
            />
          </TabsContent>

          {/* WHATSAPP TAB */}
          <TabsContent value="whatsapp">
            <WhatsAppTab 
              whatsappStatus={whatsappStatus}
              whatsappQR={whatsappQR}
              whatsappGroups={whatsappGroups}
              whatsappTarget={whatsappTarget}
              whatsappTargetInput={whatsappTargetInput}
              setWhatsappTargetInput={setWhatsappTargetInput}
              onJoinGroup={joinWhatsAppGroup}
              onConnect={connectWhatsApp}
              onSaveTarget={saveWhatsAppTarget}
              sendingEnabled={whatsappSendingEnabled}
              onRefreshStatus={fetchWhatsAppStatus}
            />
          </TabsContent>
        </Tabs>
      </main>

      {/* Menu Item Dialog */}
      <Dialog open={showMenuDialog} onOpenChange={setShowMenuDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingItem ? 'Editar Item' : 'Adicionar Item ao Cardápio'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nome *</Label>
              <Input 
                value={newItem.name} 
                onChange={(e) => setNewItem({...newItem, name: e.target.value})}
                placeholder="Ex: Café Expresso"
              />
            </div>
            <div>
              <Label>Descrição</Label>
              <Input 
                value={newItem.description} 
                onChange={(e) => setNewItem({...newItem, description: e.target.value})}
                placeholder="Ex: Café forte e encorpado"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Preço *</Label>
                <Input 
                  type="text"
                  inputMode="decimal"
                  value={newItem.price} 
                  onChange={(e) => {
                    // Accept comma OR dot for decimal, keep only numbers and a single separator
                    let v = e.target.value.replace(/[^\d.,]/g, '');
                    // Replace comma with dot, but only keep first separator
                    v = v.replace(',', '.');
                    const parts = v.split('.');
                    if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
                    setNewItem({...newItem, price: v});
                  }}
                  placeholder="0,50"
                />
              </div>
              <div>
                <Label>Categoria</Label>
                <Select value={newItem.category} onValueChange={(v) => setNewItem({...newItem, category: v})}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione a categoria" />
                  </SelectTrigger>
                  <SelectContent>
                    {menuCategories.map(cat => (
                      <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {!editingItem && (
              <div>
                <Label>Loja *</Label>
                <Select value={newItem.store} onValueChange={(v) => setNewItem({...newItem, store: v})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="runner">Runner</SelectItem>
                    <SelectItem value="gym-londres">GYM Londres</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div>
              <Label>URL da Imagem (opcional)</Label>
              <Input 
                value={newItem.image_url} 
                onChange={(e) => setNewItem({...newItem, image_url: e.target.value})}
                placeholder="https://..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowMenuDialog(false)}>Cancelar</Button>
            <Button 
              className="bg-brand-600 hover:bg-brand-700" 
              onClick={handleSaveMenuItem}
              disabled={!newItem.name || !newItem.price}
            >
              {editingItem ? 'Salvar' : 'Adicionar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Products Dialog */}
      <ProductsDialog 
        isOpen={productsDialog.open}
        onClose={() => setProductsDialog({ ...productsDialog, open: false })}
        title={productsDialog.title}
        products={productsDialog.products}
        type={productsDialog.type}
      />

      {/* Hidden Clear Data Dialog */}
      <Dialog open={showClearDialog} onOpenChange={setShowClearDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <Trash2 className="h-5 w-5" />
              Limpar Todos os Dados
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Esta ação irá apagar <strong>todos os pedidos e histórico</strong> de todas as lojas. Esta ação não pode ser desfeita.
            </p>
            <Input
              type="password"
              placeholder="Digite a senha de administrador"
              value={clearPassword}
              onChange={(e) => setClearPassword(e.target.value)}
            />
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowClearDialog(false); setClearPassword(''); }}>
                Cancelar
              </Button>
              <Button 
                variant="destructive" 
                className="flex-1" 
                onClick={handleClearData}
                disabled={isClearing || !clearPassword}
              >
                {isClearing ? 'Apagando...' : 'Apagar Tudo'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prazo Customer Dialog */}
      <Dialog open={showPrazoDialog} onOpenChange={setShowPrazoDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5 text-amber-600" />
              Cadastrar Cliente Prazo
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nome *</Label>
              <Input 
                value={newPrazoCustomer.name} 
                onChange={(e) => setNewPrazoCustomer({...newPrazoCustomer, name: e.target.value})}
                placeholder="Nome do cliente"
              />
            </div>
            <div>
              <Label>Telefone (opcional)</Label>
              <Input 
                value={newPrazoCustomer.phone} 
                onChange={(e) => setNewPrazoCustomer({...newPrazoCustomer, phone: e.target.value})}
                placeholder="(00) 00000-0000"
              />
            </div>
            <div>
              <Label>Observações (opcional)</Label>
              <Input 
                value={newPrazoCustomer.notes} 
                onChange={(e) => setNewPrazoCustomer({...newPrazoCustomer, notes: e.target.value})}
                placeholder="Ex: Paga toda sexta"
              />
            </div>
            <div>
              <Label>Loja *</Label>
              <Select 
                value={newPrazoCustomer.store} 
                onValueChange={(v) => setNewPrazoCustomer({...newPrazoCustomer, store: v})}
              >
                <SelectTrigger data-testid="prazo-new-customer-store">
                  <SelectValue placeholder="Selecione a loja" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="runner">🏃 Runner</SelectItem>
                  <SelectItem value="gym-londres">🏋️ GYM Londres</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                O cliente aparecerá no Prazo (Fiado) dessa loja na hora do pedido.
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => { setShowPrazoDialog(false); setNewPrazoCustomer({ name: '', phone: '', notes: '', store: 'runner' }); }}>
                Cancelar
              </Button>
              <Button 
                className="flex-1 bg-amber-600 hover:bg-amber-700" 
                onClick={handleAddPrazoCustomer}
                disabled={!newPrazoCustomer.name || !newPrazoCustomer.store}
              >
                Cadastrar
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Adicional Dialog */}
      <Dialog open={showAdicionalDialog} onOpenChange={setShowAdicionalDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PlusCircle className="h-5 w-5 text-brand-600" />
              {editingAdicional ? 'Editar Adicional' : 'Novo Adicional'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nome do Adicional</Label>
              <Input
                value={newAdicional.name}
                onChange={(e) => setNewAdicional({ ...newAdicional, name: e.target.value })}
                placeholder="Ex: Ovos, Mel, Queijo..."
              />
            </div>
            <div>
              <Label>Preço (R$)</Label>
              <Input
                type="number"
                step="0.01"
                min="0"
                value={newAdicional.price}
                onChange={(e) => setNewAdicional({ ...newAdicional, price: e.target.value })}
                placeholder="0.00"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => setShowAdicionalDialog(false)}>
                Cancelar
              </Button>
              <Button className="flex-1" onClick={handleSaveAdicional}>
                {editingAdicional ? 'Salvar' : 'Criar'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Expense Dialog with AI Analysis */}
      <Dialog open={showExpenseDialog} onOpenChange={setShowExpenseDialog}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5 text-red-600" />
              {analyzedExpense ? 'Confirmar Gasto' : 'Adicionar Gasto'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {/* Image Upload Section */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Camera className="h-4 w-4" />
                Foto do Comprovante (opcional)
              </Label>
              <input
                type="file"
                accept="image/*"
                onChange={handleExpenseImageChange}
                className="hidden"
                id="expense-image-input"
              />
              {expenseImagePreview ? (
                <div className="relative">
                  <img 
                    src={expenseImagePreview} 
                    alt="Comprovante" 
                    className="w-full h-32 object-cover rounded-lg border"
                  />
                  <div className="absolute bottom-2 right-2 flex gap-1">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => document.getElementById('expense-image-input').click()}
                    >
                      Trocar
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      className="bg-brand-600 hover:bg-brand-700"
                      onClick={handleAnalyzeExpense}
                      disabled={isAnalyzing}
                    >
                      {isAnalyzing ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                          Analisando...
                        </>
                      ) : (
                        <>
                          <Upload className="h-4 w-4 mr-1" />
                          Analisar com IA
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  className="w-full h-24 border-dashed flex flex-col gap-2"
                  onClick={() => document.getElementById('expense-image-input').click()}
                >
                  <Camera className="h-6 w-6 text-muted-foreground" />
                  <span className="text-sm">Tirar foto ou selecionar imagem</span>
                </Button>
              )}
              <p className="text-xs text-muted-foreground">
                Envie uma foto da nota fiscal ou recibo para análise automática por IA
              </p>
            </div>

            {/* AI Analysis Result */}
            {analyzedExpense && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <p className="text-sm font-medium text-green-700 mb-1">✓ Análise da IA concluída</p>
                <p className="text-xs text-green-600">
                  Confiança: {analyzedExpense.confidence || 'média'} - Verifique os dados abaixo antes de salvar.
                </p>
              </div>
            )}

            {/* Form Fields */}
            <div>
              <Label>Descrição *</Label>
              <Input 
                value={newExpense.description} 
                onChange={(e) => setNewExpense({...newExpense, description: e.target.value})}
                placeholder="Ex: Compra de ingredientes"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Valor (R$) *</Label>
                <Input 
                  type="number" 
                  step="0.01"
                  value={newExpense.amount} 
                  onChange={(e) => setNewExpense({...newExpense, amount: e.target.value})}
                  placeholder="0.00"
                />
              </div>
              <div>
                <Label>Categoria</Label>
                <select 
                  value={newExpense.category} 
                  onChange={(e) => setNewExpense({...newExpense, category: e.target.value})}
                  className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {EXPENSE_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Loja</Label>
                <select 
                  value={newExpense.store} 
                  onChange={(e) => setNewExpense({...newExpense, store: e.target.value})}
                  className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="all">Todas as Lojas</option>
                  <option value="runner">Runner</option>
                  <option value="gym-londres">GYM Londres</option>
                </select>
              </div>
            </div>
            <div>
              <Label>Observações</Label>
              <Input 
                value={newExpense.notes} 
                onChange={(e) => setNewExpense({...newExpense, notes: e.target.value})}
                placeholder="Ex: Nota fiscal #123"
              />
            </div>
            <DialogFooter className="flex-col sm:flex-col gap-2">
              <Button 
                className="w-full bg-red-600 hover:bg-red-700" 
                onClick={handleSaveExpense}
                disabled={!newExpense.description || !newExpense.amount}
              >
                Salvar Gasto
              </Button>
              <Button 
                variant="outline" 
                className="w-full" 
                onClick={() => {
                  setShowExpenseDialog(false);
                  setNewExpense({ description: '', amount: '', category: 'outros', store: 'all', notes: '' });
                  setExpenseImage(null);
                  setExpenseImagePreview(null);
                  setAnalyzedExpense(null);
                }}
              >
                Cancelar
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* Manual Sale Dialog (Lançamento Manual de Vendas) */}
      <Dialog open={showManualSaleDialog} onOpenChange={setShowManualSaleDialog}>
        <DialogContent className="max-w-md" data-testid="manual-sale-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-emerald-600" />
              Lançar Venda Manual
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <p className="text-xs text-muted-foreground">
              Use para registrar totais de turno (ex.: vendas da manhã não digitadas pedido a pedido).
              Conta no caixa, KPIs e gráficos como uma venda normal.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Loja *</Label>
                <select
                  className="w-full border rounded-md px-2 py-2 text-sm bg-background"
                  value={newManualSale.store}
                  onChange={(e) => setNewManualSale({ ...newManualSale, store: e.target.value })}
                  data-testid="manual-sale-store"
                >
                  <option value="runner">Runner</option>
                  <option value="gym-londres">GYM Londres</option>
                </select>
              </div>
              <div>
                <Label>Turno *</Label>
                <select
                  className="w-full border rounded-md px-2 py-2 text-sm bg-background"
                  value={newManualSale.period}
                  onChange={(e) => setNewManualSale({ ...newManualSale, period: e.target.value })}
                  data-testid="manual-sale-period"
                >
                  <option value="manha">Manhã</option>
                  <option value="tarde">Tarde</option>
                  <option value="noite">Noite</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Forma de Pagamento *</Label>
                <select
                  className="w-full border rounded-md px-2 py-2 text-sm bg-background"
                  value={newManualSale.payment_method}
                  onChange={(e) => setNewManualSale({ ...newManualSale, payment_method: e.target.value })}
                  data-testid="manual-sale-payment"
                >
                  <option value="cash">Dinheiro</option>
                  <option value="pix">PIX</option>
                  <option value="credit">Crédito</option>
                  <option value="debit">Débito</option>
                  <option value="voucher">Voucher</option>
                </select>
              </div>
              <div>
                <Label>Valor (R$) *</Label>
                <Input
                  type="text"
                  inputMode="decimal"
                  placeholder="600,55"
                  value={newManualSale.amount}
                  onChange={(e) => {
                    let v = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
                    const parts = v.split('.');
                    if (parts.length > 2) v = parts[0] + '.' + parts.slice(1).join('');
                    setNewManualSale({ ...newManualSale, amount: v });
                  }}
                  data-testid="manual-sale-amount"
                />
              </div>
            </div>

            <div>
              <Label>Data (opcional — padrão hoje)</Label>
              <Input
                type="date"
                value={newManualSale.date}
                onChange={(e) => setNewManualSale({ ...newManualSale, date: e.target.value })}
                data-testid="manual-sale-date"
              />
            </div>

            <div>
              <Label>Descrição (opcional)</Label>
              <Input
                type="text"
                placeholder="Ex.: Vendas balcão manhã"
                value={newManualSale.description}
                onChange={(e) => setNewManualSale({ ...newManualSale, description: e.target.value })}
                data-testid="manual-sale-description"
              />
            </div>

            <Button
              className="w-full bg-emerald-600 hover:bg-emerald-700"
              disabled={!newManualSale.amount || savingManualSale}
              onClick={handleSaveManualSale}
              data-testid="manual-sale-submit"
            >
              {savingManualSale ? 'Lançando…' : 'Lançar Venda'}
            </Button>

            {manualSales.length > 0 && (
              <div className="pt-2 border-t mt-2">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Últimas vendas manuais ({manualSales.length})
                </p>
                <div className="max-h-40 overflow-y-auto space-y-1" data-testid="manual-sales-list">
                  {manualSales.slice(0, 10).map((s) => (
                    <div key={s.id} className="flex items-center justify-between text-xs bg-muted/40 rounded px-2 py-1.5">
                      <div className="flex-1 min-w-0">
                        <p className="truncate font-medium">
                          {s.store === 'runner' ? 'Runner' : 'GYM'} · R$ {Number(s.total).toFixed(2)}
                          <span className="text-muted-foreground ml-1">
                            ({s.payment_method} · {s.pickup_time})
                          </span>
                        </p>
                        <p className="text-[10px] text-muted-foreground truncate">
                          {new Date(s.created_at).toLocaleString('pt-BR')} — {s.customer_name}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-red-500 hover:bg-red-50"
                        onClick={() => handleDeleteManualSale(s.id)}
                        data-testid={`manual-sale-delete-${s.id}`}
                        title="Excluir esta venda manual"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* AI Chat Dialog for Expense Analysis */}
      <Dialog open={showExpenseChat} onOpenChange={(open) => { if (!open) closeExpenseChat(); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5 text-brand-600" />
              Adicionar Gasto com IA
            </DialogTitle>
          </DialogHeader>
          
          {/* Image Upload or Preview */}
          {expenseImages.length > 0 || expenseImagePreview ? (
            <div className="flex gap-2 overflow-x-auto py-1">
              {expenseImages.length > 0 ? (
                expenseImages.map((img, idx) => (
                  <div key={idx} className="w-16 h-16 rounded-lg overflow-hidden border flex-shrink-0">
                    <img src={img} alt={`Nota ${idx + 1}`} className="w-full h-full object-cover" />
                  </div>
                ))
              ) : (
                <div className="w-full h-20 rounded-lg overflow-hidden border">
                  <img src={expenseImagePreview} alt="Comprovante" className="w-full h-full object-cover" />
                </div>
              )}
              {expenseImages.length > 0 && (
                <span className="text-xs text-muted-foreground self-center px-2">{expenseImages.length} foto(s)</span>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={handleExpenseImageChange}
                className="hidden"
                id="chat-expense-image-input"
              />
              <Button
                type="button"
                variant="outline"
                className="w-full h-20 border-dashed flex flex-col gap-1"
                onClick={() => document.getElementById('chat-expense-image-input').click()}
              >
                <Camera className="h-6 w-6 text-muted-foreground" />
                <span className="text-sm">📷 Selecionar foto(s) das notas</span>
                <span className="text-xs text-muted-foreground">Pode selecionar várias</span>
              </Button>
            </div>
          )}
          
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto space-y-3 py-2 max-h-52 min-h-16">
            {chatMessages.map((msg, idx) => (
              <div 
                key={idx} 
                className={`p-3 rounded-lg text-sm ${
                  msg.role === 'user' 
                    ? 'bg-brand-100 ml-8' 
                    : msg.role === 'system'
                    ? 'bg-gray-100 text-center text-muted-foreground'
                    : 'bg-secondary mr-8'
                }`}
              >
                {msg.content.split('\n').map((line, lidx) => (
                  <p key={lidx} className="whitespace-pre-wrap">
                    {line.replace(/\*\*(.*?)\*\*/g, (_, text) => text)}
                  </p>
                ))}
              </div>
            ))}
            {isAnalyzing && (
              <div className="flex items-center gap-2 text-muted-foreground text-sm justify-center py-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                🔍 Lendo nota com IA...
              </div>
            )}
          </div>
          
          {/* Chat Input - ALWAYS show when images are loaded */}
          {(expenseImages.length > 0 || expenseImagePreview) && (
            <div className="space-y-2 mt-2">
              <div className="flex gap-2">
                <Input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder={isAnalyzing ? "Pode digitar enquanto a IA analisa..." : "Ex: 35 fornecedor, 22 mercado, 6 suplemento"}
                  onKeyDown={(e) => e.key === 'Enter' && !isAnalyzing && pendingExpensesList.length > 0 && handleChatSubmit()}
                  autoFocus
                />
                <Button 
                  onClick={handleChatSubmit}
                  disabled={!chatInput.trim() || isAnalyzing || pendingExpensesList.length === 0}
                  className="bg-brand-600 hover:bg-brand-700"
                >
                  Salvar
                </Button>
              </div>
              {isAnalyzing && chatInput.trim() && (
                <p className="text-xs text-green-600">✓ Guardado! Será processado quando a IA terminar.</p>
              )}
            </div>
          )}
          
          {/* Quick category buttons */}
          {(awaitingCategory || (expenseImages.length > 0 && !isAnalyzing)) && pendingExpensesList.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {EXPENSE_CATEGORIES.map(cat => (
                <Button
                  key={cat}
                  variant="outline"
                  size="sm"
                  className="text-xs h-7"
                  onClick={() => { setChatInput(prev => prev ? `${prev}, ${cat}` : cat); }}
                >
                  {cat}
                </Button>
              ))}
            </div>
          )}
          
          <DialogFooter className="mt-2">
            <Button variant="outline" className="w-full" onClick={closeExpenseChat}>
              {awaitingCategory ? 'Cancelar' : 'Fechar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Contador Export Modal */}
      <Dialog open={showContadorModal} onOpenChange={setShowContadorModal}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-xl">
              <DollarSign className="h-6 w-6 text-green-600" />
              Relatório para Contador
            </DialogTitle>
          </DialogHeader>
          
          {contadorExportData && (
            <div className="space-y-4">
              {/* Período e Resumo */}
              <div className="bg-gradient-to-r from-green-50 to-blue-50 rounded-xl p-4 border">
                <h3 className="font-bold text-lg mb-2">{contadorExportData.titulo}</h3>
                <p className="text-sm text-muted-foreground">
                  Período: {contadorExportData.periodo.mes_nome}/{contadorExportData.periodo.ano}
                </p>
                <p className="text-xs text-muted-foreground">
                  {contadorExportData.periodo.data_inicio} a {contadorExportData.periodo.data_fim}
                </p>
              </div>

              {/* Resumo Geral */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-green-100 rounded-lg p-3 text-center">
                  <p className="text-xs text-green-700">Receita Total</p>
                  <p className="text-xl font-bold text-green-700">
                    R$ {contadorExportData.resumo_geral.receita_total.toFixed(2)}
                  </p>
                </div>
                <div className="bg-red-100 rounded-lg p-3 text-center">
                  <p className="text-xs text-red-700">Despesas Total</p>
                  <p className="text-xl font-bold text-red-700">
                    R$ {contadorExportData.resumo_geral.despesas_total.toFixed(2)}
                  </p>
                </div>
                <div className="bg-blue-100 rounded-lg p-3 text-center">
                  <p className="text-xs text-blue-700">Lucro Bruto</p>
                  <p className="text-xl font-bold text-blue-700">
                    R$ {contadorExportData.resumo_geral.lucro_bruto.toFixed(2)}
                  </p>
                  <p className="text-[10px] text-blue-600">
                    Margem: {contadorExportData.resumo_geral.margem_lucro_percentual}%
                  </p>
                </div>
              </div>

              {/* Resumo por Loja */}
              <div className="grid grid-cols-2 gap-3">
                <div className="border rounded-lg p-3">
                  <h4 className="font-semibold text-sm flex items-center gap-1 mb-2">
                    <span>🏃</span> Runner
                  </h4>
                  <p className="text-lg font-bold text-purple-600">
                    R$ {contadorExportData.resumo_por_loja?.runner?.receita?.toFixed(2) || '0.00'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {contadorExportData.resumo_por_loja?.runner?.pedidos || 0} pedidos
                  </p>
                </div>
                <div className="border rounded-lg p-3">
                  <h4 className="font-semibold text-sm flex items-center gap-1 mb-2">
                    <span>🏋️</span> GYM Londres
                  </h4>
                  <p className="text-lg font-bold text-orange-600">
                    R$ {contadorExportData.resumo_por_loja?.gym_londres?.receita?.toFixed(2) || '0.00'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {contadorExportData.resumo_por_loja?.gym_londres?.pedidos || 0} pedidos
                  </p>
                </div>
              </div>

              {/* Receita por Forma de Pagamento */}
              <div className="border rounded-lg p-3">
                <h4 className="font-semibold text-sm mb-2">Receita por Forma de Pagamento</h4>
                <div className="grid grid-cols-6 gap-2 text-center text-xs">
                  <div className="bg-blue-50 rounded p-2">
                    <p className="text-muted-foreground">PIX</p>
                    <p className="font-bold">R$ {contadorExportData.receita_por_forma_pagamento_consolidado?.pix?.toFixed(2)}</p>
                  </div>
                  <div className="bg-green-50 rounded p-2">
                    <p className="text-muted-foreground">Débito</p>
                    <p className="font-bold">R$ {contadorExportData.receita_por_forma_pagamento_consolidado?.debito?.toFixed(2)}</p>
                  </div>
                  <div className="bg-purple-50 rounded p-2">
                    <p className="text-muted-foreground">Crédito</p>
                    <p className="font-bold">R$ {contadorExportData.receita_por_forma_pagamento_consolidado?.credito?.toFixed(2)}</p>
                  </div>
                  <div className="bg-yellow-50 rounded p-2">
                    <p className="text-muted-foreground">Dinheiro</p>
                    <p className="font-bold">R$ {contadorExportData.receita_por_forma_pagamento_consolidado?.dinheiro?.toFixed(2)}</p>
                  </div>
                  <div className="bg-orange-50 rounded p-2">
                    <p className="text-muted-foreground">Prazo</p>
                    <p className="font-bold">R$ {contadorExportData.receita_por_forma_pagamento_consolidado?.prazo_fiado?.toFixed(2)}</p>
                  </div>
                  <div className="bg-pink-50 rounded p-2">
                    <p className="text-muted-foreground">Voucher</p>
                    <p className="font-bold">R$ {contadorExportData.receita_por_forma_pagamento_consolidado?.voucher?.toFixed(2)}</p>
                  </div>
                </div>
              </div>

              {/* Observações Fiscais */}
              <div className="bg-yellow-50 rounded-lg p-3 border border-yellow-200">
                <h4 className="font-semibold text-sm mb-2 text-yellow-800">Informações Fiscais</h4>
                <div className="text-xs space-y-1 text-yellow-700">
                  <p><strong>Regime:</strong> {contadorExportData.observacoes_fiscais?.regime_tributario}</p>
                  <p><strong>NCM Padrão:</strong> {contadorExportData.observacoes_fiscais?.ncm_padrao_alimentos}</p>
                  <p><strong>CSOSN:</strong> {contadorExportData.observacoes_fiscais?.csosn_padrao}</p>
                  <p><strong>CFOP:</strong> {contadorExportData.observacoes_fiscais?.cfop_venda_interna}</p>
                </div>
              </div>

              {/* Email do Contador */}
              <div className="border rounded-lg p-3">
                <Label className="text-sm font-semibold">📧 Enviar por E-mail</Label>
                <div className="flex gap-2 mt-2">
                  <Input
                    type="email"
                    placeholder="contador@email.com"
                    value={contadorEmail}
                    onChange={(e) => setContadorEmail(e.target.value)}
                    className="flex-1"
                  />
                  <Button variant="default" className="bg-blue-600 hover:bg-blue-700" onClick={handleSendContadorEmail} disabled={!contadorEmail}>
                    Enviar E-mail
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  O relatório será enviado diretamente para o e-mail do contador
                </p>
              </div>
            </div>
          )}

          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => setShowContadorModal(false)}>
              Fechar
            </Button>
            <Button onClick={handleDownloadContadorReport} className="bg-green-600 hover:bg-green-700">
              <DollarSign className="h-4 w-4 mr-1" /> Baixar Relatório JSON
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
