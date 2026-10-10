import { Filters, Section, api, kc, num, right, td, th } from "../lib";

export const dynamic = "force-dynamic";

type Style = { product_id: number; name: string; brand: string; stock: number; units_12m: number; units_4w: number; sell_through: number | null; weeks_of_cover: number | null; stock_value: number };
type Stock = {
  styles: { reorder: Style[]; markdown: Style[] };
  broken_curves: { product_id: number; name: string; brand: string; sizes_at_zero: number; stock: number }[];
  dead_stock: { buckets: { bucket: string; variants: number; units: number; value: number }[]; top: { product_id: number; name: string; brand: string; units: number; value: number; days_since_sale: number | null }[] };
};

const pc = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)} %`);
const wk = (v: number | null) => (v === null ? "—" : `${v.toFixed(1)} t`);

function StyleTable({ rows }: { rows: Style[] }) {
  if (!rows.length) return <p style={{ color: "#666" }}>Nic k zobrazení.</p>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead><tr><th style={th}>Produkt</th><th style={{ ...th, ...right }}>Sklad</th><th style={{ ...th, ...right }}>Prodej</th><th style={{ ...th, ...right }}>Prodáno z celku</th><th style={{ ...th, ...right }}>Zásoba</th></tr></thead>
      <tbody>{rows.map((s) => (
        <tr key={s.product_id}>
          <td style={td}><a href={`/sklad/${s.product_id}`}>{s.name}</a><div style={{ color: "#666", fontSize: 12 }}>{s.brand}</div></td>
          <td style={{ ...td, ...right }}>{num(s.stock)}</td><td style={{ ...td, ...right }}>{num(s.units_12m)}</td>
          <td style={{ ...td, ...right }}>{pc(s.sell_through)}</td><td style={{ ...td, ...right }}>{wk(s.weeks_of_cover)}</td>
        </tr>
      ))}</tbody>
    </table>
  );
}

export default async function Sklad({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const brand = (await searchParams).brand ?? "";
  const [d, brands] = await Promise.all([api<Stock>(`/stock${brand ? `?brand=${encodeURIComponent(brand)}` : ""}`), api<string[]>("/brands")]);
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <h1 style={{ fontSize: 20, margin: 0 }}>Sklad</h1>
      <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>Co doobjednat, zlevnit nebo přestat nakupovat. „Prodáno z celku“ = prodáno za 12 měsíců ÷ (prodáno + na skladě); „Zásoba“ = týdny pokrytí podle prodeje za poslední 4 týdny.</p>
      <Filters brand={brand} brands={brands} withPeriod={false} />
      <Section title="Doobjednat (zásoba pod 8 týdnů, řazeno podle prodeje)"><StyleTable rows={d.styles.reorder} /></Section>
      <Section title="Rozbité velikostní řady">
        {d.broken_curves.length ? (
          <table style={{ width: "100%", borderCollapse: "collapse" }}><tbody>{d.broken_curves.map((b) => (
            <tr key={b.product_id}><td style={td}><a href={`/sklad/${b.product_id}`}>{b.name}</a> <span style={{ color: "#666" }}>{b.brand}</span></td><td style={{ ...td, ...right }}>{b.sizes_at_zero} z 3 top velikostí na nule</td><td style={{ ...td, ...right }}>{num(b.stock)} ks</td></tr>
          ))}</tbody></table>
        ) : <p style={{ color: "#666" }}>Žádné.</p>}
      </Section>
      <Section title="Zlevnit nebo přestat nakupovat (nízký prodej, hodně zboží)"><StyleTable rows={d.styles.markdown} /></Section>
      <Section title="Mrtvý sklad (bez prodeje 90+ dní)">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Stáří</th><th style={{ ...th, ...right }}>Variant</th><th style={{ ...th, ...right }}>Kusů</th><th style={{ ...th, ...right }}>Hodnota</th></tr></thead>
          <tbody>{d.dead_stock.buckets.map((b) => (
            <tr key={b.bucket}><td style={td}>{b.bucket}</td><td style={{ ...td, ...right }}>{num(b.variants)}</td><td style={{ ...td, ...right }}>{num(b.units)}</td><td style={{ ...td, ...right }}>{kc(b.value)}</td></tr>
          ))}</tbody>
        </table>
        <h3 style={{ fontSize: 14, margin: "12px 0 4px" }}>Největší hodnota</h3>
        <table style={{ width: "100%", borderCollapse: "collapse" }}><tbody>{d.dead_stock.top.map((t) => (
          <tr key={t.product_id}><td style={td}><a href={`/sklad/${t.product_id}`}>{t.name}</a> <span style={{ color: "#666" }}>{t.brand}</span></td><td style={{ ...td, ...right }}>{num(t.units)} ks</td><td style={{ ...td, ...right }}>{kc(t.value)}</td></tr>
        ))}</tbody></table>
      </Section>
    </main>
  );
}
