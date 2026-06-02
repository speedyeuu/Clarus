import type { Metadata } from "next";
import "./globals.css";
import UpdatedAt from "@/components/UpdatedAt";

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
          {/* Top navigation bar */}
          <header style={{
            borderBottom: "1px solid var(--border)",
            background: "rgba(7,7,15,0.8)",
            backdropFilter: "blur(12px)",
            position: "sticky",
            top: 0,
            zIndex: 50,
          }}>
            <div style={{
              maxWidth: "1600px",
              margin: "0 auto",
              padding: "0 24px",
              height: "56px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}>
              {/* Logo — jen wordmark */}
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{ fontWeight: "700", fontSize: "16px", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                  Clarus
                </span>
              </div>

              {/* Right: live dot + updated time */}
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <div className="live-dot" />
                  <UpdatedAt />
                </div>
              </div>
            </div>
          </header>

          {/* Main content */}
          <main style={{ maxWidth: "1600px", margin: "0 auto", padding: "24px" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
