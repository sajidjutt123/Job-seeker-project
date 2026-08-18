import { Suspense } from "react";

import { LoadingBlock } from "@/components/ui/states";

import { ResetPasswordForm } from "./ResetPasswordForm";

export const metadata = { title: "Set a new password", robots: { index: false, follow: false } };

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
