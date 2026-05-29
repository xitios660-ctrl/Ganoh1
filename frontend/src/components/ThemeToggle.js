import React, { useRef } from 'react';
import { Sun, Moon, Droplet } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export const ThemeToggle = ({ className = '' }) => {
  const { theme, toggleTheme, transitioning } = useTheme();
  const btnRef = useRef(null);

  const handleClick = (e) => {
    if (transitioning) return;
    const rect = btnRef.current?.getBoundingClientRect();
    const x = rect ? rect.left + rect.width / 2 : e.clientX;
    const y = rect ? rect.top + rect.height / 2 : e.clientY;
    toggleTheme({ x, y });
  };

  const isDark = theme === 'dark';

  return (
    <button
      ref={btnRef}
      onClick={handleClick}
      disabled={transitioning}
      aria-label={isDark ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
      data-testid="theme-toggle"
      className={`relative h-10 w-10 rounded-full flex items-center justify-center overflow-hidden transition-all duration-300 ${
        isDark
          ? 'bg-white/[0.06] border border-white/15 text-[#a8d96b] hover:bg-white/[0.10]'
          : 'bg-white border border-border/40 text-[#7fb84a] hover:border-[#a8d96b]/60 hover:shadow-md'
      } ${className}`}
    >
      {/* Sun icon (visible in dark mode, since clicking switches to light) */}
      <Sun
        className={`absolute h-5 w-5 transition-all duration-500 ${
          isDark ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 rotate-90 scale-50'
        }`}
      />
      {/* Moon icon (visible in light mode) */}
      <Moon
        className={`absolute h-5 w-5 transition-all duration-500 ${
          !isDark ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-50'
        }`}
      />
      {/* Drop icon visible while transition is happening */}
      {transitioning && (
        <Droplet className="absolute h-4 w-4 animate-bounce text-[#a8d96b]" />
      )}
    </button>
  );
};

export default ThemeToggle;
