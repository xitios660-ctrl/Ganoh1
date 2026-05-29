import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { Checkbox } from '../components/ui/checkbox';
import { RadioGroup, RadioGroupItem } from '../components/ui/radio-group';
import { Label } from '../components/ui/label';
import { useCart } from '../context/CartContext';
import { useTheme } from '../context/ThemeContext';
import { Plus, Minus, Clock, X, Milk } from 'lucide-react';

// Categorias que NÃO mostram adicionais
const CATEGORIES_WITHOUT_ADICIONAIS = [
  "Bebidas Quentes",
  "Bebidas Geladas",
  "Suplementos"
];

export const ProductModal = ({ item, isOpen, onClose, adicionais = [], milkOptions = [] }) => {
  const { addItem } = useCart();
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const [quantity, setQuantity] = useState(1);
  const [selectedAdicionais, setSelectedAdicionais] = useState([]);
  const [selectedMilk, setSelectedMilk] = useState('');

  // Check if item has "leite" in name or description
  const hasMilk = item && (
    item.name?.toLowerCase().includes('leite') ||
    item.description?.toLowerCase().includes('leite') ||
    item.name?.toLowerCase().includes('vitamina') ||
    item.name?.toLowerCase().includes('shake') ||
    item.name?.toLowerCase().includes('cappuccino') ||
    item.name?.toLowerCase().includes('café com leite') ||
    item.name?.toLowerCase().includes('chocolate quente')
  );

  // Reset milk selection when item changes
  useEffect(() => {
    if (hasMilk && milkOptions.length > 0) {
      setSelectedMilk(milkOptions[0]?.name || 'Integral');
    } else {
      setSelectedMilk('');
    }
  }, [item, hasMilk, milkOptions]);

  if (!item) return null;

  const showAdicionais = !CATEGORIES_WITHOUT_ADICIONAIS.includes(item.category);

  const formatPrice = (price) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(price);
  };

  const handleAdicionalToggle = (adicional) => {
    setSelectedAdicionais(prev => {
      const exists = prev.find(a => a.id === adicional.id);
      if (exists) {
        return prev.filter(a => a.id !== adicional.id);
      }
      return [...prev, adicional];
    });
  };

  const adicionaisTotal = selectedAdicionais.reduce((sum, a) => sum + a.price, 0);
  const itemTotal = (item.price + adicionaisTotal) * quantity;

  const handleAddToCart = () => {
    let itemName = item.name;
    
    // Add milk type if selected
    if (hasMilk && selectedMilk) {
      itemName = `${itemName} (Leite ${selectedMilk})`;
    }
    
    // Add adicionais
    if (selectedAdicionais.length > 0) {
      itemName = `${itemName} + ${selectedAdicionais.map(a => a.name).join(', ')}`;
    }
    
    const itemWithAdicionais = {
      ...item,
      name: itemName,
      price: item.price + adicionaisTotal,
      milk_type: selectedMilk || null
    };
    
    // Add the product with the selected quantity in a single call (fixes off-by-one bug)
    addItem(itemWithAdicionais, quantity);
    
    setQuantity(1);
    setSelectedAdicionais([]);
    setSelectedMilk(hasMilk && milkOptions.length > 0 ? milkOptions[0]?.name : '');
    onClose();
  };

  const handleClose = () => {
    setQuantity(1);
    setSelectedAdicionais([]);
    setSelectedMilk(hasMilk && milkOptions.length > 0 ? milkOptions[0]?.name : '');
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className={`sm:max-w-md p-0 overflow-hidden gap-0 border-0 ${isDark ? 'bg-[#0a0a0a] text-white' : 'bg-white'}`}>
        {/* Header — seamless, no border */}
        <div className="flex items-center justify-between p-4">
          <h2 className={`font-heading text-xl font-light ${isDark ? 'text-white' : 'text-foreground'}`}>
            {item.name}
          </h2>
          <button
            onClick={handleClose}
            className={`h-8 w-8 rounded-full flex items-center justify-center transition-colors ${isDark ? 'bg-white/[0.06] hover:bg-white/[0.12] text-white' : 'bg-black/[0.04] hover:bg-black/[0.08] text-muted-foreground'}`}
            data-testid="close-modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content Section */}
        <div className="p-5 pt-0">
          {/* Product Info */}
          <div className="mb-4">
            <p className={`text-sm mb-3 ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>
              {item.description}
            </p>
            <div className="flex items-center gap-3">
              <span className="text-2xl font-bold text-[#7fb84a]">
                {formatPrice(item.price)}
              </span>
              <div className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded-full ${isDark ? 'bg-white/[0.06] text-white/70' : 'bg-black/[0.04] text-muted-foreground'}`}>
                <Clock className="h-3 w-3" />
                <span>~{item.prep_time} min</span>
              </div>
            </div>
          </div>

          {/* Milk Type Section */}
          {hasMilk && milkOptions.length > 0 && (
            <div className={`pt-4 mb-4 ${isDark ? 'border-t border-white/5' : 'border-t border-black/[0.04]'}`}>
              <h3 className={`font-semibold mb-3 text-sm flex items-center gap-2 ${isDark ? 'text-white' : 'text-foreground'}`}>
                <Milk className="h-4 w-4 text-[#7fb84a]" />
                Tipo de Leite
              </h3>
              <RadioGroup value={selectedMilk} onValueChange={setSelectedMilk} className="grid grid-cols-2 gap-2">
                {milkOptions.map((milk) => (
                  <div key={milk.id} className={`flex items-center space-x-2 p-2 rounded-lg cursor-pointer transition-colors ${isDark ? 'bg-white/[0.04] hover:bg-white/[0.08]' : 'bg-black/[0.02] hover:bg-black/[0.05]'}`}>
                    <RadioGroupItem value={milk.name} id={milk.id} className="text-[#7fb84a]" />
                    <Label htmlFor={milk.id} className={`text-sm cursor-pointer flex-1 ${isDark ? 'text-white/80' : ''}`}>{milk.name}</Label>
                  </div>
                ))}
              </RadioGroup>
            </div>
          )}

          {/* Adicionais Section */}
          {showAdicionais && adicionais.length > 0 && (
            <div className={`pt-4 mb-4 ${isDark ? 'border-t border-white/5' : 'border-t border-black/[0.04]'}`}>
              <h3 className={`font-semibold mb-3 text-sm ${isDark ? 'text-white' : 'text-foreground'}`}>
                Adicionais
                <span className={`font-normal ml-1 ${isDark ? 'text-white/40' : 'text-muted-foreground'}`}>
                  (opcional)
                </span>
              </h3>
              <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto">
                {adicionais.map((adicional) => {
                  const isSelected = selectedAdicionais.some(a => a.id === adicional.id);
                  return (
                    <label
                      key={adicional.id}
                      className={`flex items-center justify-between p-2.5 rounded-lg cursor-pointer transition-all text-sm ${
                        isSelected 
                          ? (isDark ? 'bg-[#a8d96b]/15 ring-1 ring-[#a8d96b]/40' : 'bg-[#a8d96b]/10 ring-1 ring-[#a8d96b]/40')
                          : (isDark ? 'bg-white/[0.04] hover:bg-white/[0.08]' : 'bg-black/[0.02] hover:bg-black/[0.05]')
                      }`}
                      data-testid={`adicional-${adicional.id}`}
                    >
                      <div className="flex items-center gap-2">
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => handleAdicionalToggle(adicional)}
                          className="h-4 w-4 data-[state=checked]:bg-[#7fb84a] data-[state=checked]:border-[#7fb84a]"
                        />
                        <span className={`font-medium ${isDark ? 'text-white' : 'text-foreground'}`}>{adicional.name}</span>
                      </div>
                      <span className="text-[#7fb84a] font-semibold text-xs">
                        +{formatPrice(adicional.price)}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {/* Quantity and Add to Cart */}
          <div className={`pt-4 ${isDark ? 'border-t border-white/5' : 'border-t border-black/[0.04]'}`}>
            <div className="flex items-center justify-between mb-4">
              <span className={`text-sm ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>Quantidade</span>
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  size="icon"
                  className={`h-9 w-9 rounded-full border-0 ${isDark ? 'bg-white/[0.06] hover:bg-white/[0.12] text-white' : 'bg-black/[0.04] hover:bg-black/[0.08]'}`}
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  disabled={quantity <= 1}
                  data-testid="decrease-quantity"
                >
                  <Minus className="h-4 w-4" />
                </Button>
                <span className={`w-6 text-center text-lg font-semibold ${isDark ? 'text-white' : ''}`}>{quantity}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className={`h-9 w-9 rounded-full border-0 ${isDark ? 'bg-white/[0.06] hover:bg-white/[0.12] text-white' : 'bg-black/[0.04] hover:bg-black/[0.08]'}`}
                  onClick={() => setQuantity(quantity + 1)}
                  data-testid="increase-quantity"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <Button 
              className="w-full h-12 text-base font-semibold bg-[#7fb84a] hover:bg-[#6ba33b] text-white border-0 rounded-xl shadow-lg shadow-[#7fb84a]/20 transition-all hover:scale-[1.01]"
              onClick={handleAddToCart}
              data-testid="add-to-cart-modal"
            >
              Adicionar · {formatPrice(itemTotal)}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
