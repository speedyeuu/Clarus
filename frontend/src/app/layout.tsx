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
              {/* Logo */}
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div style={{
                  width: "28px", height: "28px",
                  borderRadius: "6px",
                  background: "linear-gradient(135deg, #22d3a0, #0ea5e9)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "14px", fontWeight: "700", color: "#07070f",
                }}>C</div>
                <span style={{ fontWeight: "600", fontSize: "15px", color: "var(--text-primary)" }}>
                  Clarus
                </span>
                <span style={{
                  fontSize: "11px", fontWeight: "500",
                  padding: "2px 7px", borderRadius: "4px",
                  background: "var(--bullish-dim)", color: "var(--bullish)",
                }}>BETA</span>
              </div>

              {/* Right: updated date + pair */}
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <div className="live-dot" />
                  <UpdatedAt />
                </div>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "13px", fontWeight: "500",
                  color: "var(--text-primary)",
                  padding: "4px 12px",
                  background: "var(--bg-elevated)",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                }}>
                  EUR/USD
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
