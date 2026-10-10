import type { ReactNode } from "react";

export const API = process.env.API_URL ?? "http://localhost:8000";
export const TENANT = process.env.TENANT ?? "elka";

export const kc = (v: number) => `${Math.round(v).toLocaleString("cs-CZ")} Kč`;
export const num = (v: number) => Math.round(v).toLocaleString("cs-CZ");
export const pct = (v: number | null) => (v === null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v))} %`);
export const delta = (now: number, ly: number) => (ly ? ((now - ly) / ly) * 100 : null);

export async function api<T>(path: string): Promise<T> {
  const res = await fetch(`${API}/api/${TENANT}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

export const card = { background: "#fff", borderRadius: 8, padding: 16 } as const;
export const th = { textAlign: "left", fontWeight: 500, color: "#666", fontSize: 13, padding: "4px 8px" } as const;
export const td = { padding: "6px 8px", borderTop: "1px solid #eee", fontSize: 14 } as const;
export const right = { textAlign: "right" } as const;

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ ...card, marginTop: 16, overflowX: "auto" }}>
      <h2 style={{ fontSize: 16, margin: "0 0 8px" }}>{title}</h2>
      {children}
    </section>
  );
}

/** Global filters as a plain GET form: no client JS needed. */
export function Filters({ days, channel, brand, brands, withPeriod = true }: {
  days?: number; channel?: string; brand?: string; brands: string[]; withPeriod?: boolean;
}) {
  const sel = { padding: 6, fontSize: 14 } as const;
  return (
    <form style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0" }}>
      {withPeriod && (
        <select name="days" defaultValue={String(days ?? 30)} style={sel}>
          {[7, 30, 90, 365].map((d) => <option key={d} value={d}>posledních {d} dní</option>)}
        </select>
      )}
      {channel !== undefined && (
        <select name="channel" defaultValue={channel} style={sel}>
          <option value="all">Obchod + e-shop</option><option value="store">Obchod</option><option value="web">E-shop</option>
        </select>
      )}
      <select name="brand" defaultValue={brand ?? ""} style={sel}>
        <option value="">Všechny značky</option>
        {brands.map((b) => <option key={b} value={b}>{b}</option>)}
      </select>
      <button style={sel}>Použít</button>
    </form>
  );
}
