export const dynamic = "force-dynamic";

const API = process.env.API_URL ?? "http://localhost:8000";
const TENANT = process.env.TENANT ?? "elka";

const kc = (v: number) => `${Math.round(v).toLocaleString("cs-CZ")} Kč`;
const pct = (v: number | null) => (v === null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v))} %`);

type Overview = {
  tenant: string;
  facts: {
    current: Record<"total" | "store" | "web", { revenue: number; orders: number; basket: number }>;
    yoy_pct: number | null;
    wow_pct: number | null;
    margin_coverage: number;
  };
  trend: { date: string; revenue: number }[];
  alerts: { broken_size_curves: string[]; sold_out: string[]; dead_stock: number };
};

export default async function Prehled() {
  const res = await fetch(`${API}/api/${TENANT}/overview`, { cache: "no-store" });
  if (!res.ok) return <main style={{ padding: 16 }}>Data se nepodařilo načíst ({res.status}).</main>;
  const d: Overview = await res.json();
  const max = Math.max(...d.trend.map((t) => t.revenue), 1);
  const card = { background: "#fff", borderRadius: 8, padding: 16, flex: "1 1 160px" } as const;

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <h1 style={{ fontSize: 20 }}>Přehled · {d.tenant}</h1>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {(["total", "store", "web"] as const).map((k) => (
          <div key={k} style={card}>
            <div style={{ color: "#666", fontSize: 13 }}>{{ total: "Celkem", store: "Obchod", web: "E-shop" }[k]} včera</div>
            <div style={{ fontSize: 24, fontWeight: 600 }}>{kc(d.facts.current[k].revenue)}</div>
            <div style={{ color: "#666", fontSize: 13 }}>{d.facts.current[k].orders} obj. · košík {kc(d.facts.current[k].basket)}</div>
            {k === "total" && <div style={{ fontSize: 13 }}>r/r {pct(d.facts.yoy_pct)} · t/t {pct(d.facts.wow_pct)}</div>}
          </div>
        ))}
        <div style={card}>
          <div style={{ color: "#666", fontSize: 13 }}>Pokrytí marže</div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>{Math.round(d.facts.margin_coverage * 100)} %</div>
        </div>
      </div>

      <h2 style={{ fontSize: 16, marginTop: 24 }}>Tržby, posledních 30 dní</h2>
      <svg viewBox={`0 0 ${d.trend.length * 10} 80`} style={{ width: "100%", background: "#fff", borderRadius: 8 }} role="img" aria-label="Tržby za 30 dní">
        {d.trend.map((t, i) => (
          <rect key={t.date} x={i * 10 + 1} y={78 - (t.revenue / max) * 74} width={8} height={(t.revenue / max) * 74} fill="#3b6ea5">
            <title>{`${t.date}: ${kc(t.revenue)}`}</title>
          </rect>
        ))}
      </svg>

      <h2 style={{ fontSize: 16, marginTop: 24 }}>Co vyžaduje pozornost</h2>
      <ul>
        {d.alerts.broken_size_curves.length > 0 && <li>Rozbité velikostní řady: {d.alerts.broken_size_curves.join(", ")}</li>}
        {d.alerts.sold_out.length > 0 && <li>Včera došlo: {d.alerts.sold_out.join(", ")}</li>}
        {d.alerts.dead_stock > 0 && <li>{d.alerts.dead_stock} variant bez prodeje 90+ dní</li>}
      </ul>
    </main>
  );
}
