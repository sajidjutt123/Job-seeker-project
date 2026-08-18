import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/ui/states";

import { UnsubscribeClient } from "./UnsubscribeClient";

export const metadata: Metadata = {
  title: "Unsubscribe",
  description: "Stop receiving emails for a RozgarPK job alert.",
  robots: { index: false, follow: false },
};

export default function UnsubscribePage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <UnsubscribeClient />
    </Suspense>
  );
}
