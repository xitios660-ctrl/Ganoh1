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

  // Triggered by click on toggle button — origin is { x, y } of the click.
  // Important: iOS Safari can occasionally skip transitionend for clip-path.
  // The fallback timer below guarantees the UI is never left locked.
  const toggleTheme = useCallback((origin) => {
    if (transitioning) return;
    setTransitioning(true);
    userHasToggledRef.current = true;

    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    const targetColor = nextTheme === 'dark' ? '#0a0a0a' : '#fafaf7';
    const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;

    // Reduced motion and browsers without clip-path get an immediate, safe swap.
    if (prefersReducedMotion || !window.CSS?.supports?.('clip-path', 'circle(10px at 10px 10px)')) {
      setTheme(nextTheme);
      setTransitioning(false);
      return;
    }

    let overlay = overlayRef.current;
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.inset = '0';
      overlay.style.zIndex = '99999';
      overlay.style.pointerEvents = 'none';
      overlay.style.willChange = 'clip-path, opacity';
      document.body.appendChild(overlay);
      overlayRef.current = overlay;
    }

    const { x = window.innerWidth / 2, y = window.innerHeight / 2 } = origin || {};
    const maxRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    );

    overlay.style.opacity = '1';
    overlay.style.background = `radial-gradient(circle at center, ${targetColor} 70%, ${targetColor}cc 100%)`;
    overlay.style.transition = 'none';
    overlay.style.clipPath = `circle(0px at ${x}px ${y}px)`;
    // eslint-disable-next-line no-unused-expressions
    overlay.offsetHeight;

    let finished = false;
    let fallbackTimer = null;

    const finish = () => {
      if (finished) return;
      finished = true;
      if (fallbackTimer) clearTimeout(fallbackTimer);
      overlay.removeEventListener('transitionend', onTransitionEnd);

      // Apply the actual theme before uncovering the page.
      setTheme(nextTheme);
      requestAnimationFrame(() => {
        overlay.style.transition = 'opacity 160ms ease-out';
        overlay.style.opacity = '0';
        setTimeout(() => {
          overlay.style.transition = 'none';
          overlay.style.opacity = '1';
          overlay.style.clipPath = `circle(0px at ${x}px ${y}px)`;
          setTransitioning(false);
        }, 190);
      });
    };

    const onTransitionEnd = (event) => {
      if (event.target === overlay && event.propertyName === 'clip-path') finish();
    };

    overlay.addEventListener('transitionend', onTransitionEnd);
    overlay.style.transition = 'clip-path 420ms cubic-bezier(0.65, 0, 0.35, 1)';
    overlay.style.clipPath = `circle(${maxRadius}px at ${x}px ${y}px)`;

    // Hard safety net for Safari: even if transitionend never fires,
    // theme switching completes and the button is unlocked.
    fallbackTimer = setTimeout(finish, 560);
  }, [theme, transitioning]);

  useEffect(() => () => {
    const overlay = overlayRef.current;
    if (overlay?.parentNode) overlay.parentNode.removeChild(overlay);
    overlayRef.current = null;
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, transitioning }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
