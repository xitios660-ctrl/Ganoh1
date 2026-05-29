import React from 'react';
import { useCart } from '../context/CartContext';
import { useTheme } from '../context/ThemeContext';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from '../components/ui/sheet';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { Minus, Plus, Trash2, ShoppingBag } from 'lucide-react';

export const CartDrawer = ({ onCheckout }) => {
  const { items, isOpen, setIsOpen, total, updateQuantity, removeItem, itemCount } = useCart();
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const formatPrice = (price) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(price);
  };

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetContent className={`w-full sm:max-w-lg flex flex-col border-0 ${isDark ? 'bg-[#0a0a0a] text-white' : 'bg-white'}`}>
        <SheetHeader>
          <SheetTitle className={`font-heading text-2xl flex items-center gap-2 font-light ${isDark ? 'text-white' : 'text-foreground'}`}>
            <ShoppingBag className="h-6 w-6 text-[#7fb84a]" />
            Seu <span className="italic text-[#7fb84a]">Pedido</span>
          </SheetTitle>
        </SheetHeader>

        {items.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
            <div className="relative inline-block mb-4">
              <div className="absolute inset-0 -m-3 rounded-full blur-2xl bg-[#a8d96b]/15" />
              <ShoppingBag className={`relative h-16 w-16 ${isDark ? 'text-white/20' : 'text-muted-foreground/30'}`} />
            </div>
            <p className={`text-lg ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>Seu carrinho está vazio</p>
            <p className={`text-sm mt-1 ${isDark ? 'text-white/40' : 'text-muted-foreground'}`}>Adicione itens do cardápio</p>
          </div>
        ) : (
          <>
            <ScrollArea className="flex-1 -mx-6 px-6">
              <div className="space-y-3 py-4">
                {items.map((item, index) => (
                  <div
                    key={item.menu_item_id}
                    className={`flex items-center gap-4 p-3 rounded-xl animate-slideIn transition-colors ${isDark ? 'bg-white/[0.04] hover:bg-white/[0.07]' : 'bg-secondary/50 hover:bg-secondary/70'}`}
                    style={{ animationDelay: `${index * 50}ms` }}
                    data-testid={`cart-item-${item.menu_item_id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className={`font-medium truncate ${isDark ? 'text-white' : 'text-foreground'}`}>{item.name}</p>
                      <p className="text-sm text-[#7fb84a] font-semibold">
                        {formatPrice(item.price)}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Diminuir quantidade"
                        className={`h-8 w-8 rounded-full border-0 ${isDark ? 'bg-white/[0.06] hover:bg-white/[0.12] text-white' : 'bg-black/[0.04] hover:bg-black/[0.08]'}`}
                        onClick={() => updateQuantity(item.menu_item_id, item.quantity - 1)}
                        data-testid={`decrease-${item.menu_item_id}`}
                      >
                        <Minus className="h-4 w-4" />
                      </Button>
                      <span className={`w-8 text-center font-medium ${isDark ? 'text-white' : ''}`}>{item.quantity}</span>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Aumentar quantidade"
                        className={`h-8 w-8 rounded-full border-0 ${isDark ? 'bg-white/[0.06] hover:bg-white/[0.12] text-white' : 'bg-black/[0.04] hover:bg-black/[0.08]'}`}
                        onClick={() => updateQuantity(item.menu_item_id, item.quantity + 1)}
                        data-testid={`increase-${item.menu_item_id}`}
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Remover item"
                        className="h-8 w-8 text-red-400 hover:text-red-500 hover:bg-red-500/10"
                        onClick={() => removeItem(item.menu_item_id)}
                        data-testid={`remove-${item.menu_item_id}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>

            <SheetFooter className="pt-4 mt-4">
              <div className="w-full space-y-4">
                <div className="flex justify-between items-center">
                  <span className={`text-lg ${isDark ? 'text-white/60' : 'text-muted-foreground'}`}>
                    {itemCount} {itemCount === 1 ? 'item' : 'itens'}
                  </span>
                  <span className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-foreground'}`} data-testid="cart-total">
                    {formatPrice(total)}
                  </span>
                </div>

                <Button
                  className="w-full h-14 text-lg font-semibold bg-[#7fb84a] hover:bg-[#6ba33b] text-white border-0 shadow-lg shadow-[#7fb84a]/20 transition-all hover:scale-[1.01]"
                  onClick={onCheckout}
                  data-testid="checkout-button"
                >
                  Finalizar Pedido →
                </Button>
              </div>
            </SheetFooter>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
};
