import CafeShell from "../../components/CafeShell";
import DeskClient from "./DeskClient";

export default function DeskPage() {
  return (
    <CafeShell title="焚火にあたる" description="火のそばで、誰かと話せます。話した言葉は、火が消えると一緒に消えます。">
      <DeskClient />
    </CafeShell>
  );
}
