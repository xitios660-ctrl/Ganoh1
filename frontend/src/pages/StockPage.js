import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Package, AlertTriangle, RefreshCw, Home, Plus, Minus, Search } from 'lucide-react';
import { Toaster, toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LOGO_URL = "/assets/ganoh-logo.png";

const STORE_NAMES = { 'runner': 'Runner', 'gym-londres': 'GYM Londres' };

export const StockPage = () => {
  const { store } = useParams();
  const navigate = useNavigate();
  const [stock, setStock] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [updating, setUpdating] = useState({});

  useEffect(() => {
    if (store) {
      fetchStock();
      initializeStock();
    }
  }, [store]);

  const initializeStock = async () => {
    try {
      await axios.post(`${API}/stock/${store}/initialize`);
    } catch (error) {
      console.error('Error initializing stock:', error);
    }
  };

  const fetchStock = async () => {
    try {
      const response = await axios.get(`${API}/stock/${store}`);
      setStock(response.data.stock);
    } catch (error) {
      console.error('Erro:', error);
      toast.error('Erro ao carregar estoque');
    } finally {
      setIsLoading(false);
    }
  };

  const updateStock = async (menuItemId, newQuantity) => {
    if (newQuantity < 0) return;
    
    setUpdating(prev => ({ ...prev, [menuItemId]: true }));
    try {
      await axios.put(`${API}/stock/${store}/${menuItemId}`, { quantity: newQuantity });
      setStock(prev => prev.map(item => 
        item.menu_item_id === menuItemId 
          ? { ...item, quantity: newQuantity, low_stock: newQuantity <= 5 }
          : item
      ));
      toast.success('Estoque atualizado');
    } catch (error) {
      toast.error('Erro ao atualizar');
    } finally {
      setUpdating(prev => ({ ...prev, [menuItemId]: false }));
    }
  };

  const filteredStock = stock.filter(item =>
    item.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.category?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groupedStock = filteredStock.reduce((acc, item) => {
    const category = item.category || 'Outros';
    if (!acc[category]) acc[category] = [];
    acc[category].push(item);
    return acc;
  }, {});

  const lowStockCount = stock.filter(item => item.low_stock).length;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-brand-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100" data-testid="stock-page">
      <Toaster position="top-center" richColors />
      
      <header className="bg-white border-b sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" onClick={() => navigate('/')}>
                <Home className="h-5 w-5" />
              </Button>
              <div>
                <h1 className="font-heading text-lg font-bold flex items-center gap-2">
                  <Package className="h-5 w-5" /> Estoque
                </h1>
                <p className="text-xs text-muted-foreground">{STORE_NAMES[store]}</p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={fetchStock}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          
          {/* Stats */}
          <div className="flex gap-3 mb-3">
            <div className="flex-1 bg-secondary/50 rounded-lg p-2 text-center">
              <p className="text-xs text-muted-foreground">Total Produtos</p>
              <p className="text-lg font-bold">{stock.length}</p>
            </div>
            {lowStockCount > 0 && (
              <div className="flex-1 bg-red-50 rounded-lg p-2 text-center">
                <p className="text-xs text-red-600">Estoque Baixo</p>
                <p className="text-lg font-bold text-red-600">{lowStockCount}</p>
              </div>
            )}
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar produto..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-4">
        {Object.entries(groupedStock).map(([category, items]) => (
          <div key={category} className="mb-6">
            <h2 className="font-semibold text-sm text-muted-foreground mb-2">{category}</h2>
            <div className="space-y-2">
              {items.map((item) => (
                <Card key={item.menu_item_id} className={item.low_stock ? 'border-red-200 bg-red-50/50' : ''}>
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium truncate">{item.name}</span>
                          {item.low_stock && (
                            <Badge variant="destructive" className="text-xs">
                              <AlertTriangle className="h-3 w-3 mr-1" /> Baixo
                            </Badge>
                          )}
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2 ml-2">
                        <Button
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => updateStock(item.menu_item_id, item.quantity - 1)}
                          disabled={updating[item.menu_item_id] || item.quantity <= 0}
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                        <Input
                          type="number"
                          value={item.quantity}
                          onChange={(e) => updateStock(item.menu_item_id, parseInt(e.target.value) || 0)}
                          className="w-16 h-8 text-center"
                          min="0"
                        />
                        <Button
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => updateStock(item.menu_item_id, item.quantity + 1)}
                          disabled={updating[item.menu_item_id]}
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ))}

        {filteredStock.length === 0 && (
          <div className="text-center py-12">
            <Package className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-muted-foreground">Nenhum produto encontrado</p>
          </div>
        )}
      </main>
    </div>
  );
};
