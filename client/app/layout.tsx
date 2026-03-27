import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Todolist App",
  description: "A Flask and Next.js task board with MongoDB-backed authentication and a polished user dashboard.",
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
