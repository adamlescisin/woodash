import type { ReactNode } from "react";

export const metadata = { title: "woodash" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="cs">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f6f6f4", color: "#1a1a1a" }}>
        {children}
      </body>
    </html>
  );
}
