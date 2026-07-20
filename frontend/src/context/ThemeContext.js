import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const ThemeContext = createContext({ theme: 'light', toggleTheme: () => {} });

const USER_PREF_KEY = 'ganoh_theme_user';     // set only when the user explicitly toggles
const LEGACY_KEY = 'ganoh_theme';             // older app version key — preserved as fallback

// Routes kept for reference: cardápio (menu) pages used to default to dark;
// the client now wants LIGHT as the default theme on every page.
const getInitialTheme = () => {
  try {
    // Highest priority: explicit user choice
    const userPref = localStorage.getItem(USER_PREF_KEY);
    if (userPref === 'dark' || userPref === 'light') return userPref;
    return 'light';
  } catch {
    return 'light';
  }
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(getInitialTheme);
  const overlayRef = useRef(null);
  const [transitioning, setTransitioning] = useState(false);
  const userHasToggledRef = useRef(false);

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    // Only persist as USER preference if the user has toggled explicitly.
    // We still write the legacy key so other parts of the app keep working.
    try {
      localStorage.setItem(LEGACY_KEY, theme);
      if (userHasToggledRef.current) {
        localStorage.setItem(USER_PREF_KEY, theme);
      }
    } catch (e) { /* ignore */ }
  }, [theme]);

  // React to in-app navigation is no longer needed: light theme is the global
  // default and only the user's explicit toggle changes it.

  // Triggered by click on toggle button — origin is { x, y } of the click
  const toggleTheme = useCallback((origin) => {
    if (transitioning) return;
    setTransitioning(true);
    userHasToggledRef.current = true;

    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    const targetColor = nextTheme === 'dark' ? '#0a0a0a' : '#fafaf7';

    // Build overlay if not present
    let overlay = overlayRef.current;
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.inset = '0';
      overlay.style.zIndex = '99999';
      overlay.style.pointerEvents = 'none';
      overlay.style.willChange = 'clip-path';
      document.body.appendChild(overlay);
      overlayRef.current = overlay;
    }

    const { x = window.innerWidth / 2, y = 0 } = origin || {};
    const maxRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    );

    // Stage 1: water drop falling - tiny circle at top expands gently
    overlay.style.background = `radial-gradient(circle at center, ${targetColor} 70%, ${targetColor}cc 100%)`;
    overlay.style.transition = 'none';
    overlay.style.clipPath = `circle(0px at ${x}px ${y}px)`;
    // Force reflow
    // eslint-disable-next-line no-unused-expressions
    overlay.offsetHeight;

    // Stage 2: ripple expands across the screen
    overlay.style.transition = 'clip-path 850ms cubic-bezier(0.65, 0, 0.35, 1)';
    overlay.style.clipPath = `circle(${maxRadius}px at ${x}px ${y}px)`;

    // After ripple completes, swap theme and fade out overlay
    const onEnd = () => {
      overlay.removeEventListener('transitionend', onEnd);
      setTheme(nextTheme);
      // Tiny delay so React applies the theme class before fade-out
      requestAnimationFrame(() => {
        overlay.style.transition = 'opacity 250ms ease-out';
        overlay.style.opacity = '0';
        setTimeout(() => {
          overlay.style.opacity = '1';
          overlay.style.clipPath = `circle(0px at ${x}px ${y}px)`;
          setTransitioning(false);
        }, 280);
      });
    };
    overlay.addEventListener('transitionend', onEnd);
  }, [theme, transitioning]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, transitioning }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
