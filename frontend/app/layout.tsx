import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Locater",
  description: "Retail and chain location aggregation map for China"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
