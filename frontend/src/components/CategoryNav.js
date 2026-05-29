import React, { useRef, useEffect } from 'react';
import { cn } from '../lib/utils';

export const CategoryNav = ({ categories, activeCategory, onCategoryChange }) => {
  const navRef = useRef(null);
  const activeRef = useRef(null);

  useEffect(() => {
    if (activeRef.current && navRef.current) {
      const nav = navRef.current;
      const active = activeRef.current;
      const navRect = nav.getBoundingClientRect();
      const activeRect = active.getBoundingClientRect();
      
      const scrollLeft = active.offsetLeft - navRect.width / 2 + activeRect.width / 2;
      nav.scrollTo({ left: scrollLeft, behavior: 'smooth' });
    }
  }, [activeCategory]);

  return (
    <nav 
      ref={navRef}
      className="flex gap-3 overflow-x-auto pb-4 scrollbar-hide -mx-4 px-4"
      role="tablist"
      aria-label="Categorias do cardápio"
    >
      {categories.map((category) => {
        const isActive = activeCategory === category;
        return (
          <button
            key={category}
            ref={isActive ? activeRef : null}
            onClick={() => onCategoryChange(category)}
            role="tab"
            aria-selected={isActive}
            data-testid={`category-${category.replace(/\s+/g, '-').toLowerCase()}`}
            className={cn(
              "whitespace-nowrap px-5 py-2.5 rounded-full border transition-all duration-200 font-medium text-sm",
              isActive
                ? "bg-brand-600 text-white border-brand-600 shadow-md"
                : "bg-white text-foreground border-border hover:bg-brand-50 hover:border-brand-200"
            )}
          >
            {category}
          </button>
        );
      })}
    </nav>
  );
};
