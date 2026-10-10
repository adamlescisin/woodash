import { Section, api, card, delta, kc, num, pct, right, td, th } from "../lib";

export const dynamic = "force-dynamic";

type Source = { source: string; medium: string; revenue: number; revenue_ly: number; orders: number; new_customers: number };
type Channel = { channel: string; sessions: number; sessions_ly: number; users: number; add_to_carts: number; checkouts: number };
type Data = {
  period: { start: string; end: string };
  sources: { rows: Source[]; attribution_coverage: number | null };
  traffic: { rows: Channel[]; web_orders: number; sessions: number; conversion_rate: number | null; data_from: string | null; data_to: string | null };
};

const pc = (v: number | null, d = 0) => (v === null ? "—" : `${(v * 100).toFixed(d)} %`);

export default async function Kanaly({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const days = Number((await searchParams).days ?? 30);
  const d = await api<Data>(`/channels?days=${days}`);
  const t = d.traffic;
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <h1 style={{ fontSize: 20, margin: 0 }}>Kanály</h1>
      <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>Odkud přicházejí zákazníci · {d.period.start} až {d.period.end}, srovnání se stejným obdobím loni. Tržby a objednávky jsou z WooCommerce (zdroj pravdy), návštěvnost z GA4.</p>
      <form style={{ margin: "8px 0" }}>
        <select name="days" defaultValue={String(days)} style={{ padding: 6, fontSize: 14 }}>
          {[7, 30, 90, 365].map((x) => <option key={x} value={x}>posledních {x} dní</option>)}
        </select>{" "}
        <button style={{ padding: 6, fontSize: 14 }}>Použít</button>
      </form>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Návštěvy (GA4)</div><div style={{ fontSize: 24, fontWeight: 600 }}>{num(t.sessions)}</div></div>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Objednávky e-shopu</div><div style={{ fontSize: 24, fontWeight: 600 }}>{num(t.web_orders)}</div></div>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Konverze (obj. ÷ návštěvy)</div><div style={{ fontSize: 24, fontWeight: 600 }}>{pc(t.conversion_rate, 1)}</div></div>
        <div style={{ ...card, flex: "1 1 160px" }}><div style={{ color: "#666", fontSize: 13 }}>Objednávky se zdrojem</div><div style={{ fontSize: 24, fontWeight: 600 }}>{pc(d.sources.attribution_coverage)}</div><div style={{ fontSize: 12, color: "#666" }}>podíl tržeb s Order Attribution</div></div>
      </div>
      <Section title="E-shop: tržby podle zdroje (Order Attribution)">
        {d.sources.rows.length ? (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>Zdroj / médium</th><th style={{ ...th, ...right }}>Tržba</th><th style={{ ...th, ...right }}>r/r</th><th style={{ ...th, ...right }}>Obj.</th><th style={{ ...th, ...right }}>Noví zákazníci</th></tr></thead>
            <tbody>{d.sources.rows.map((s) => (
              <tr key={s.source + s.medium}>
                <td style={td}>{s.source}{s.medium ? ` / ${s.medium}` : ""}</td><td style={{ ...td, ...right }}>{kc(s.revenue)}</td>
                <td style={{ ...td, ...right }}>{pct(delta(s.revenue, s.revenue_ly))}</td><td style={{ ...td, ...right }}>{num(s.orders)}</td><td style={{ ...td, ...right }}>{num(s.new_customers)}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : <p style={{ color: "#666" }}>V tomto období nejsou žádné objednávky e-shopu.</p>}
      </Section>
      <Section title="Návštěvnost a nákupní trychtýř podle kanálu (GA4)">
        {t.rows.length ? (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>Kanál</th><th style={{ ...th, ...right }}>Návštěvy</th><th style={{ ...th, ...right }}>r/r</th><th style={{ ...th, ...right }}>Do košíku</th><th style={{ ...th, ...right }}>Pokladna</th></tr></thead>
            <tbody>{t.rows.map((c) => (
              <tr key={c.channel}>
                <td style={td}>{c.channel}</td><td style={{ ...td, ...right }}>{num(c.sessions)}</td>
                <td style={{ ...td, ...right }}>{pct(delta(c.sessions, c.sessions_ly))}</td><td style={{ ...td, ...right }}>{num(c.add_to_carts)}</td><td style={{ ...td, ...right }}>{num(c.checkouts)}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : <p style={{ color: "#666" }}>Žádná data z GA4 pro toto období.</p>}
        {t.data_from && <p style={{ color: "#666", fontSize: 12 }}>GA4 data máme od {t.data_from} do {t.data_to}. Consent mode skrývá část návštěv, proto jsou skutečné návštěvy vyšší.</p>}
      </Section>
    </main>
  );
}
