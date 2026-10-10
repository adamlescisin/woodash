import { Filters, Section, api, card, delta, kc, num, pct, right, td, th } from "../lib";

export const dynamic = "force-dynamic";

type Row = { name: string; revenue: number; revenue_ly: number; units: number };
type Sales = {
  period: { start: string; end: string };
  brands: Row[]; categories: Row[];
  top_products: { product_id: number; name: string; brand: string; revenue: number; units: number }[];
  heatmap: { weekday: number; hour: number; revenue: number; orders: number }[];
  basket: { basket: number; basket_ly: number; units_per_order: number; orders: number; orders_ly: number };
};

const DAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];

function RankTable({ rows }: { rows: Row[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead><tr><th style={th}>Název</th><th style={{ ...th, ...right }}>Tržba</th><th style={{ ...th, ...right }}>r/r</th><th style={{ ...th, ...right }}>ks</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name}>
            <td style={td}>{r.name}</td><td style={{ ...td, ...right }}>{kc(r.revenue)}</td>
            <td style={{ ...td, ...right }}>{pct(delta(r.revenue, r.revenue_ly))}</td><td style={{ ...td, ...right }}>{num(r.units)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Heatmap({ cells }: { cells: Sales["heatmap"] }) {
  if (!cells.length) return <p style={{ color: "#666" }}>Žádné prodeje v obchodě v tomto období.</p>;
  const hours = Array.from({ length: 12 }, (_, i) => i + 8); // 8–19
  const max = Math.max(...cells.map((c) => c.revenue), 1);
  const at = (d: number, h: number) => cells.find((c) => c.weekday === d && c.hour === h)?.revenue ?? 0;
  return (
    <table style={{ borderCollapse: "collapse", fontSize: 12 }} aria-label="Tržby v obchodě podle dne a hodiny">
      <thead><tr><th />{hours.map((h) => <th key={h} style={{ fontWeight: 400, padding: 2 }}>{h}</th>)}</tr></thead>
      <tbody>
        {DAYS.map((label, i) => (
          <tr key={label}>
            <td style={{ paddingRight: 6 }}>{label}</td>
            {hours.map((h) => {
              const v = at(i + 1, h);
              return <td key={h} title={`${label} ${h}:00 — ${kc(v)}`} style={{ width: 28, height: 24, background: `rgba(59,110,165,${v ? 0.12 + 0.88 * (v / max) : 0.04})` }} />;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function Prodej({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const days = Number(sp.days ?? 30), channel = sp.channel ?? "all", brand = sp.brand ?? "";
  const q = new URLSearchParams({ days: String(days), channel, ...(brand ? { brand } : {}) });
  const [d, brands] = await Promise.all([api<Sales>(`/sales?${q}`), api<string[]>("/brands")]);
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <h1 style={{ fontSize: 20, margin: 0 }}>Prodej</h1>
      <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>Co, kde a kdy se prodává · {d.period.start} až {d.period.end}, srovnání se stejným obdobím loni</p>
      <Filters days={days} channel={channel} brand={brand} brands={brands} />
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Průměrný košík</div><div style={{ fontSize: 24, fontWeight: 600 }}>{kc(d.basket.basket)}</div><div style={{ fontSize: 13 }}>r/r {pct(delta(d.basket.basket, d.basket.basket_ly))}</div></div>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Objednávky</div><div style={{ fontSize: 24, fontWeight: 600 }}>{num(d.basket.orders)}</div><div style={{ fontSize: 13 }}>r/r {pct(delta(d.basket.orders, d.basket.orders_ly))}</div></div>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Kusů na objednávku</div><div style={{ fontSize: 24, fontWeight: 600 }}>{d.basket.units_per_order.toFixed(1)}</div></div>
      </div>
      <Section title="Značky"><RankTable rows={d.brands} /></Section>
      <Section title="Kategorie"><RankTable rows={d.categories} /></Section>
      <Section title="Nejprodávanější produkty">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>{d.top_products.map((p) => (
            <tr key={p.product_id}><td style={td}><a href={`/sklad/${p.product_id}`}>{p.name}</a> <span style={{ color: "#666" }}>{p.brand}</span></td><td style={{ ...td, ...right }}>{kc(p.revenue)}</td><td style={{ ...td, ...right }}>{num(p.units)} ks</td></tr>
          ))}</tbody>
        </table>
      </Section>
      <Section title="Obchod: tržby podle dne a hodiny"><Heatmap cells={d.heatmap} /></Section>
    </main>
  );
}
