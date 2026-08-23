import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FaceSentry | Privacy-First Windows Face Authentication",
  description: "Autonomous, local biometric presence monitoring and auto-lock security engine.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#080c14] text-slate-100 antialiased selection:bg-cyan-500 selection:text-black">
        {children}
      </body>
    </html>
  );
}
