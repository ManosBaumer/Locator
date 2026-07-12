import type { Metadata, Viewport } from "next";
import { mituBrandFont } from "@/lib/fonts";
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

/** Extend layout into iOS safe areas so the map shows behind Safari’s chrome. */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#ebe6dc"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={mituBrandFont.variable}>
      <body className={mituBrandFont.className}>{children}</body>
    </html>
  );
}
