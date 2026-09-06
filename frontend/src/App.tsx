import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import Dashboard from "./screens/Dashboard";
import Tutor from "./screens/Tutor";
import Library from "./screens/Library";
import Plan from "./screens/Plan";
import QuizSetup from "./pages/quiz/QuizSetup";
import QuizTake from "./pages/quiz/QuizTake";
import QuizResults from "./pages/quiz/QuizResults";
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
        <Route path="/" element={<Dashboard />} />
        <Route path="/tutor" element={<Tutor />} />
        <Route path="/library" element={<Library />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/quiz" element={<QuizSetup />} />
        <Route path="/quiz/take" element={<QuizTake />} />
        <Route path="/quiz/take/:assessmentId" element={<QuizTake />} />
        <Route path="/quiz/results" element={<QuizResults />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <DataProvider>
        <NotificationProvider>
          <BrowserRouter>
            <div className="app-layout">
            <Sidebar />
            <main className="main-area">
              <AnimatedRoutes />
            </main>
            <ChatPanel />
          </div>
        </BrowserRouter>
        <Toaster />
      </NotificationProvider>
    </DataProvider>
  </ThemeProvider>
  );
}
