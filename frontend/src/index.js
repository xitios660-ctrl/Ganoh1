import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Register Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then((registration) => {
        console.log('SW registered:', registration.scope);
        
        // Listen for messages from Service Worker
        navigator.serviceWorker.addEventListener('message', (event) => {
          if (event.data.type === 'SYNC_ORDERS') {
            window.dispatchEvent(new CustomEvent('syncOfflineOrders'));
          }
          if (event.data.type === 'OFFLINE_ORDER') {
            window.dispatchEvent(new CustomEvent('offlineOrderSaved', { 
              detail: event.data.order 
            }));
          }
        });
      })
      .catch((error) => {
        console.log('SW registration failed:', error);
      });
  });
}
