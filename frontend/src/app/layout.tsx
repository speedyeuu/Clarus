import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clarus",
  description: "Clarus – real-time fundamentální scoring EUR/USD páru. Úrokové sazby, inflace, COT, PMI a více.",
  keywords: ["EUR/USD", "forex", "fundamentální analýza", "swing trading", "Clarus"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="cs" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <div className="min-h-screen" style={{ background: "var(--bg-primary)" }}>
          <main style={{ maxWidth: "1600px", margin: "0 auto", padding: "24px" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
