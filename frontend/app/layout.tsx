import type { Metadata } from "next";
import { SITE_DESCRIPTION, SITE_FAVICON_SRC, SITE_NAME } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: SITE_NAME,
  description: SITE_DESCRIPTION,
  icons: {
    icon: SITE_FAVICON_SRC,
    apple: SITE_FAVICON_SRC
  }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
