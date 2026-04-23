import { PresentationView } from "./components/PresentationView";
import { SetupScreen } from "./components/SetupScreen";
import { usePresentationStore } from "./store/usePresentationStore";

export default function App() {
  const deck = usePresentationStore((s) => s.deck);
  return deck ? <PresentationView /> : <SetupScreen />;
}
