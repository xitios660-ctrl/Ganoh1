// Offline support utilities for GANOH Café Bistrô
// Uses localStorage for simplicity, with Service Worker for caching

const OFFLINE_ORDERS_KEY = 'ganoh_offline_orders';
const MENU_CACHE_KEY = 'ganoh_menu_cache';
const OFFLINE_STATUS_KEY = 'ganoh_offline_status';

// Check if online
export const isOnline = () => navigator.onLine;

// Save order offline
export const saveOrderOffline = (orderData) => {
  const offlineOrders = getOfflineOrders();
  const offlineOrder = {
    ...orderData,
    offline_id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    created_at: new Date().toISOString(),
    status: 'pending_sync'
  };
  offlineOrders.push(offlineOrder);
  localStorage.setItem(OFFLINE_ORDERS_KEY, JSON.stringify(offlineOrders));
  return offlineOrder;
};

// Get offline orders
export const getOfflineOrders = () => {
  try {
    return JSON.parse(localStorage.getItem(OFFLINE_ORDERS_KEY) || '[]');
  } catch {
    return [];
  }
};

// Get pending orders count
export const getPendingOrdersCount = () => {
  return getOfflineOrders().filter(o => o.status === 'pending_sync').length;
};

// Clear synced orders
export const clearSyncedOrders = (syncedIds) => {
  const offlineOrders = getOfflineOrders();
  const remaining = offlineOrders.filter(order => !syncedIds.includes(order.offline_id));
  localStorage.setItem(OFFLINE_ORDERS_KEY, JSON.stringify(remaining));
};

// Sync offline orders when back online
export const syncOfflineOrders = async (apiUrl) => {
  const offlineOrders = getOfflineOrders().filter(o => o.status === 'pending_sync');
  if (offlineOrders.length === 0) return { synced: 0, failed: 0 };

  try {
    const response = await fetch(`${apiUrl}/api/orders/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(offlineOrders)
    });
    
    if (response.ok) {
      const result = await response.json();
      const syncedIds = result.synced_orders
        .filter(r => r.synced)
        .map(r => r.offline_id);
      clearSyncedOrders(syncedIds);
      return {
        synced: syncedIds.length,
        failed: offlineOrders.length - syncedIds.length
      };
    }
  } catch (error) {
    console.error('Sync failed:', error);
  }
  
  return { synced: 0, failed: offlineOrders.length };
};

// Cache menu data for offline use
export const cacheMenuData = (store, menuData) => {
  try {
    const cache = JSON.parse(localStorage.getItem(MENU_CACHE_KEY) || '{}');
    cache[store] = {
      data: menuData,
      timestamp: Date.now()
    };
    localStorage.setItem(MENU_CACHE_KEY, JSON.stringify(cache));
    
    // Also tell Service Worker to cache
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({
        type: 'CACHE_MENU',
        store,
        data: menuData
      });
    }
  } catch (error) {
    console.error('Cache menu failed:', error);
  }
};

// Get cached menu data
export const getCachedMenu = (store) => {
  try {
    const cache = JSON.parse(localStorage.getItem(MENU_CACHE_KEY) || '{}');
    const storeCache = cache[store];
    if (storeCache) {
      // Cache valid for 24 hours
      const isValid = (Date.now() - storeCache.timestamp) < 24 * 60 * 60 * 1000;
      if (isValid) {
        return storeCache.data;
      }
    }
    return null;
  } catch {
    return null;
  }
};

// Set offline status
export const setOfflineStatus = (isOffline) => {
  localStorage.setItem(OFFLINE_STATUS_KEY, JSON.stringify({ isOffline, timestamp: Date.now() }));
};

// Get offline status
export const getOfflineStatus = () => {
  try {
    const status = JSON.parse(localStorage.getItem(OFFLINE_STATUS_KEY) || '{}');
    return status.isOffline || false;
  } catch {
    return false;
  }
};

// Listen for online/offline events
export const setupOfflineListener = (onOnline, onOffline) => {
  const handleOnline = () => {
    setOfflineStatus(false);
    onOnline();
  };
  
  const handleOffline = () => {
    setOfflineStatus(true);
    onOffline();
  };
  
  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);
  
  // Also listen for sync events from Service Worker
  const handleSyncEvent = () => {
    if (isOnline()) {
      onOnline();
    }
  };
  window.addEventListener('syncOfflineOrders', handleSyncEvent);
  
  return () => {
    window.removeEventListener('online', handleOnline);
    window.removeEventListener('offline', handleOffline);
    window.removeEventListener('syncOfflineOrders', handleSyncEvent);
  };
};

// Request background sync
export const requestBackgroundSync = async () => {
  if ('serviceWorker' in navigator && 'sync' in window.SyncManager) {
    const registration = await navigator.serviceWorker.ready;
    await registration.sync.register('sync-orders');
  }
};
