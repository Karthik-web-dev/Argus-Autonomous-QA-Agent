import { DashboardPage } from "./DashboardPage";
import LandingPage from "./LandingPage";
import HomePage from "./HomePage";
import DashboardRunPage from "./DashboardRunPage";
import ChatRunPage from "./ChatRunPage";
import ReplayPage from "./ReplayPage";
import "./styles/globals.css";

export default function App() {
  const path = window.location.pathname;

  if (path === "/dashboard") return <DashboardPage />;
  if (path === "/") return <LandingPage />;
  if (path === "/replay") return <ReplayPage />;
  const dashboardRun = path.match(/^\/app\/dashboard\/([^/]+)\/?$/);
  if (dashboardRun) return <DashboardRunPage id={decodeURIComponent(dashboardRun[1])} />;
  const chatRun = path.match(/^\/app\/chat\/([^/]+)\/?$/);
  if (chatRun) return <ChatRunPage id={decodeURIComponent(chatRun[1])} />;
  if (path === "/app") return <HomePage />;

  return <main className="shell"><p className="eyebrow">404</p><h1>Page not found</h1><a href="/">Return to Argus</a></main>;
}
