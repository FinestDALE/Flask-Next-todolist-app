import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mini Todo",
  description: "A small modern todo list app powered by Next.js and Flask.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
