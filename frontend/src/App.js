import "@/index.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { CartProvider } from "./context/CartContext";
import { ThemeProvider } from "./context/ThemeContext";
import { MenuPage } from "./pages/MenuPage";
import { OrderTrackingPage } from "./pages/OrderTrackingPage";
import { KitchenPage } from "./pages/KitchenPage";
import { GestorPage } from "./pages/GestorPage";
import { StoreSelectorPage } from "./pages/StoreSelectorPage";
import { AuthPage } from "./pages/AuthPage";
import LiveDashboardPage from "./pages/LiveDashboardPage";
import { StaffAccessPage } from "./pages/StaffAccessPage";
import { StockPage } from "./pages/StockPage";
import GanohCursor from "./components/GanohCursor";
import { OfflineBanner } from "./components/OfflineBanner";
import { BackgroundMusic } from "./components/BackgroundMusic";

function App() {
  return (
    <ThemeProvider>
      <CartProvider>
        <BrowserRouter>
          <OfflineBanner />
          <BackgroundMusic />
          <GanohCursor />
          <Routes>
            {/* Store Selector */}
            <Route path="/" element={<StoreSelectorPage />} />
            
            {/* Store-specific routes */}
            <Route path="/:store" element={<MenuPage />} />
            <Route path="/:store/pedido/:orderId" element={<OrderTrackingPage />} />
            <Route path="/:store/cozinha" element={<KitchenPage />} />
            <Route path="/:store/estoque" element={<StockPage />} />
            
            {/* Auth page - login/register */}
            <Route path="/auth" element={<AuthPage />} />

            {/* Staff access - kitchen + gestor separated */}
            <Route path="/equipe" element={<StaffAccessPage />} />
            
            {/* Gestor (manager) panel */}
            <Route path="/gestor/dashboard" element={<GestorPage />} />
            
            {/* Live cinematic dashboard (for in-store TV display) */}
            <Route path="/:store/live" element={<LiveDashboardPage />} />
            
            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </CartProvider>
    </ThemeProvider>
  );
}

export default App;
