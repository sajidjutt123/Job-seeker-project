import { Suspense } from "react";

import { LoadingBlock } from "@/components/ui/states";

import { VerifyEmailClient } from "./VerifyEmailClient";

export const metadata = { title: "Verify your email", robots: { index: false, follow: false } };

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <VerifyEmailClient />
    </Suspense>
  );
}
