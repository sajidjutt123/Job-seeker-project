import type { Metadata, Viewport } from "next";

import { AuthProvider } from "@/components/auth/AuthProvider";
import { Footer } from "@/components/layout/Footer";
import { Navbar } from "@/components/layout/Navbar";
import { ToastProvider } from "@/components/ui/Toast";

import "./globals.css";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "RozgarPK — Find the right job in Pakistan",
    template: "%s | RozgarPK",
  },
  description:
    "Search jobs from across Pakistan in one place. Government, private, remote and internship " +
    "opportunities gathered from authorised sources, with a direct link to every original posting.",
  keywords: [
    "jobs in Pakistan", "government jobs", "remote jobs Pakistan", "internships Pakistan",
    "jobs in Lahore", "jobs in Karachi", "jobs in Islamabad", "fresh graduate jobs",
  ],
  applicationName: "RozgarPK",
  openGraph: {
    type: "website",
    locale: "en_PK",
    siteName: "RozgarPK",
    title: "RozgarPK — Find the right job in Pakistan",
    description:
      "Jobs from multiple authorised sources across Pakistan, searchable in one place.",
    url: SITE_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: "RozgarPK — Find the right job in Pakistan",
    description: "Jobs from multiple authorised sources across Pakistan, searchable in one place.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  alternates: { canonical: "/" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f766e",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col antialiased">
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <AuthProvider>
          <ToastProvider>
            <Navbar />
            <main id="main-content" className="flex-1">
              {children}
            </main>
            <Footer />
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
