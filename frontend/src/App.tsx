import { LoginScreen } from "./components/LoginScreen";
import { PresentationView } from "./components/PresentationView";
import { SetupScreen } from "./components/SetupScreen";
import { useAuthStore } from "./store/useAuthStore";
import { usePresentationStore } from "./store/usePresentationStore";

export default function App() {
  const authed = useAuthStore((s) => s.authed);
  const deck = usePresentationStore((s) => s.deck);

  if (!authed) return <LoginScreen />;
  return deck ? <PresentationView /> : <SetupScreen />;
}
