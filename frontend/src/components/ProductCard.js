import React, { useRef, useState } from 'react';
import { Button } from '../components/ui/button';
import { Plus, Clock } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export const ProductCard = React.memo(({ item, onClick }) => {
  const cardRef = useRef(null);
  const [transform, setTransform] = useState('');
  const [glowPos, setGlowPos] = useState({ x: 50, y: 50 });
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const formatPrice = (price) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(price);
  };

  // 3D tilt effect (subtle, only on devices with hover)
  const handleMouseMove = (e) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const rx = ((y - cy) / cy) * -4; // max 4 degrees
    const ry = ((x - cx) / cx) * 4;
    setTransform(`perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) translateZ(0)`);
    setGlowPos({ x: (x / rect.width) * 100, y: (y / rect.height) * 100 });
  };

  const handleMouseLeave = () => {
    setTransform('');
    setGlowPos({ x: 50, y: 50 });
  };

  return (
    <div 
      ref={cardRef}
      className={`relative rounded-2xl border p-4 transition-all duration-300 cursor-pointer group overflow-hidden ${
        isDark 
          ? 'bg-white/[0.03] border-white/10 hover:border-[#a8d96b]/50 backdrop-blur-sm' 
          : 'bg-white border-border/40 hover:border-[#a8d96b]/60'
      }`}
      style={{
        transform,
        transformStyle: 'preserve-3d',
        transition: transform ? 'transform 0.15s ease-out, border-color 0.3s, background-color 0.3s' : 'transform 0.4s ease, border-color 0.3s, background-color 0.3s',
        boxShadow: transform 
          ? (isDark 
              ? '0 12px 32px -8px rgba(168, 217, 107, 0.25), 0 4px 12px -2px rgba(0,0,0,0.4)'
              : '0 12px 32px -8px rgba(168, 217, 107, 0.18), 0 4px 12px -2px rgba(0,0,0,0.06)')
          : (isDark ? '0 1px 3px rgba(0,0,0,0.3)' : '0 1px 3px rgba(0,0,0,0.04)')
      }}
      data-testid={`product-card-${item.id}`}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      {/* Glow follow cursor */}
      <div 
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none rounded-2xl"
        style={{
          background: `radial-gradient(circle at ${glowPos.x}% ${glowPos.y}%, rgba(168,217,107,${isDark ? 0.18 : 0.12}), transparent 60%)`
        }}
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className={`font-semibold mb-1 group-hover:text-[#a8d96b] transition-colors ${isDark ? 'text-white' : 'text-foreground'}`}>
            {item.name}
          </h3>
          <p className={`text-sm line-clamp-2 mb-2 ${isDark ? 'text-white/50' : 'text-muted-foreground'}`}>
            {item.description}
          </p>
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold text-[#a8d96b]">
              {formatPrice(item.price)}
            </span>
            <div className={`flex items-center gap-1 text-xs ${isDark ? 'text-white/40' : 'text-muted-foreground'}`}>
              <Clock className="h-3 w-3" />
              <span>~{item.prep_time} min</span>
            </div>
          </div>
        </div>
        
        <Button
          size="icon"
          className="h-9 w-9 rounded-full bg-[#7fb84a] hover:bg-[#6ba33b] shadow-md shrink-0 group-hover:scale-110 transition-transform"
          onClick={(e) => {
            e.stopPropagation();
            onClick();
          }}
          data-testid={`add-to-cart-${item.id}`}
          aria-label={`Adicionar ${item.name} ao carrinho`}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}, (prev, next) => prev.item.id === next.item.id && prev.item.price === next.item.price && prev.item.name === next.item.name && prev.onClick === next.onClick);
