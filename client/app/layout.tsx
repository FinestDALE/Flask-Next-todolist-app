import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Task Board",
  description: "A cleaner Flask and Next.js task board with validated models and a GitHub-inspired UI.",
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
