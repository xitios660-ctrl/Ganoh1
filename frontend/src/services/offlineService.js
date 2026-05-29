// Offline Orders Service
// Saves orders locally when offline and syncs when online

const OFFLINE_ORDERS_KEY = 'ganoh_offline_orders';
const API_BASE = process.env.REACT_APP_BACKEND_URL;

// Check if we're online
export const isOnline = () => {
  return navigator.onLine;
};

// Get offline orders from localStorage
export const getOfflineOrders = () => {
  try {
    const orders = localStorage.getItem(OFFLINE_ORDERS_KEY);
    return orders ? JSON.parse(orders) : [];
  } catch (e) {
    console.error('Error getting offline orders:', e);
    return [];
  }
};

// Save order to offline storage
export const saveOfflineOrder = (order) => {
  try {
    const orders = getOfflineOrders();
    const offlineOrder = {
      ...order,
      id: `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      offline: true,
      savedAt: new Date().toISOString(),
      synced: false
    };
    orders.push(offlineOrder);
    localStorage.setItem(OFFLINE_ORDERS_KEY, JSON.stringify(orders));
    console.log('Order saved offline:', offlineOrder.id);
    return offlineOrder;
  } catch (e) {
    console.error('Error saving offline order:', e);
    throw e;
  }
};

// Remove synced order from offline storage
export const removeOfflineOrder = (orderId) => {
  try {
    const orders = getOfflineOrders();
    const filtered = orders.filter(o => o.id !== orderId);
    localStorage.setItem(OFFLINE_ORDERS_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.error('Error removing offline order:', e);
  }
};

// Mark order as synced
export const markOrderSynced = (orderId) => {
  try {
    const orders = getOfflineOrders();
    const updated = orders.map(o => 
      o.id === orderId ? { ...o, synced: true, syncedAt: new Date().toISOString() } : o
    );
    localStorage.setItem(OFFLINE_ORDERS_KEY, JSON.stringify(updated));
  } catch (e) {
    console.error('Error marking order synced:', e);
  }
};

// Sync all offline orders to server
export const syncOfflineOrders = async () => {
  const orders = getOfflineOrders().filter(o => !o.synced);
  
  if (orders.length === 0) {
    console.log('No offline orders to sync');
    return { synced: 0, failed: 0 };
  }
  
  console.log(`Syncing ${orders.length} offline orders...`);
  
  let synced = 0;
  let failed = 0;
  
  for (const order of orders) {
    try {
      // Prepare order for API (remove offline-specific fields)
      const orderToSync = {
        store: order.store,
        customer_name: order.customer_name,
        phone: order.phone,
        items: order.items,
        total: order.total,
        payment_method: order.payment_method,
        pickup_time: order.pickup_time,
        notes: order.notes,
        offline_id: order.id,
        offline_saved_at: order.savedAt
      };
      
      const response = await fetch(`${API_BASE}/api/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderToSync)
      });
      
      if (response.ok) {
        markOrderSynced(order.id);
        synced++;
        console.log(`Order ${order.id} synced successfully`);
      } else {
        failed++;
        console.error(`Failed to sync order ${order.id}:`, await response.text());
      }
    } catch (e) {
      failed++;
      console.error(`Error syncing order ${order.id}:`, e);
    }
  }
  
  // Clean up synced orders after 24 hours
  cleanupSyncedOrders();
  
  return { synced, failed };
};

// Clean up old synced orders (older than 24 hours)
const cleanupSyncedOrders = () => {
  try {
    const orders = getOfflineOrders();
    const now = new Date();
    const filtered = orders.filter(o => {
      if (!o.synced) return true;
      const syncedAt = new Date(o.syncedAt || o.savedAt);
      const hoursDiff = (now - syncedAt) / (1000 * 60 * 60);
      return hoursDiff < 24;
    });
    localStorage.setItem(OFFLINE_ORDERS_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.error('Error cleaning up synced orders:', e);
  }
};

// Create order - handles both online and offline
export const createOrder = async (orderData) => {
  // Try to send online first
  if (isOnline()) {
    try {
      const response = await fetch(`${API_BASE}/api/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData)
      });
      
      if (response.ok) {
        const result = await response.json();
        // Also try to sync any pending offline orders
        syncOfflineOrders().catch(console.error);
        return { success: true, order: result, offline: false };
      }
    } catch (e) {
      console.log('Online order failed, saving offline:', e);
    }
  }
  
  // Save offline if online failed or we're offline
  const offlineOrder = saveOfflineOrder(orderData);
  return { success: true, order: offlineOrder, offline: true };
};

// Initialize online/offline listeners
export const initOfflineSync = () => {
  // Sync when coming back online
  window.addEventListener('online', () => {
    console.log('Back online - syncing orders...');
    syncOfflineOrders().then(result => {
      if (result.synced > 0) {
        console.log(`Synced ${result.synced} orders`);
      }
    });
  });
  
  // Log when going offline
  window.addEventListener('offline', () => {
    console.log('Now offline - orders will be saved locally');
  });
  
  // Initial sync if online
  if (isOnline()) {
    syncOfflineOrders().catch(console.error);
  }
};

export default {
  isOnline,
  getOfflineOrders,
  saveOfflineOrder,
  removeOfflineOrder,
  syncOfflineOrders,
  createOrder,
  initOfflineSync
};
