import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingBlock } from "@/components/ui/states";

import { RegisterForm } from "./RegisterForm";

export const metadata: Metadata = {
  title: "Create your account",
  description: "Create a free RozgarPK account to save jobs, set alerts and get matched roles.",
  robots: { index: false, follow: true },
};

export default function RegisterPage() {
  return (
    <Suspense fallback={<LoadingBlock />}>
      <RegisterForm />
    </Suspense>
  );
}
