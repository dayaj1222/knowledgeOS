import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./queryClient";
import Sidebar from "./components/Sidebar";
import Tutor from "./screens/Tutor";
import Library from "./screens/Library";
import Plan from "./screens/Plan";
import Settings from "./screens/Settings";
import { DataProvider } from "./store";
import { NotificationProvider } from "./components/notifications";
import { ThemeProvider } from "./context/ThemeContext";
import { Toaster } from "./components/ui/sonner";

// Keyed wrapper: remounts the route view on every navigation so the
// route-transition animation replays — tab switches glide instead of snapping.
function AnimatedRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="route-transition">
      <Routes location={location}>
        <Route path="/" element={<Tutor />} />
        <Route path="/library" element={<Library />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
      <DataProvider>
        <NotificationProvider>
          <BrowserRouter>
            <div className="app-layout">
            <Sidebar />
            <main className="main-area">
              <AnimatedRoutes />
            </main>
          </div>
        </BrowserRouter>
        <Toaster />
      </NotificationProvider>
      </DataProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
