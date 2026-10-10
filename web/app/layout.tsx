import type { ReactNode } from "react";

export const metadata = { title: "woodash" };

const links = [["/", "Přehled"], ["/prodej", "Prodej"], ["/kanaly", "Kanály"], ["/sklad", "Sklad"]];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="cs">
      <head><meta name="viewport" content="width=device-width, initial-scale=1" /></head>
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f6f6f4", color: "#1a1a1a" }}>
        <nav style={{ display: "flex", gap: 16, padding: "12px 16px", background: "#fff", borderBottom: "1px solid #e5e5e0", overflowX: "auto" }}>
          {links.map(([href, label]) => <a key={href} href={href} style={{ color: "#1a1a1a", textDecoration: "none", fontWeight: 600 }}>{label}</a>)}
        </nav>
        {children}
      </body>
    </html>
  );
}
