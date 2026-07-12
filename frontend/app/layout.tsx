import type { Metadata } from "next";
import { SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: SITE_NAME,
  description: SITE_DESCRIPTION
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
