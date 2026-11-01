import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "AcadSync · Your semester, in sync",
  description: "Turn academic emails into a clear, organized calendar.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
