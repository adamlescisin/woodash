import { Section, api, num, right, td, th } from "../../lib";

export const dynamic = "force-dynamic";

type Size = { variant_id: number; sku: string; size: string; colour: string | null; stock: number; units_90d: number; units_total: number };

export default async function Style({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const d = await api<{ sizes: Size[] }>(`/stock/${id}`);
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <a href="/sklad">← Sklad</a>
      <h1 style={{ fontSize: 20 }}>Velikostní řada</h1>
      <Section title="Velikosti: sklad a prodej">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Velikost</th><th style={th}>Barva</th><th style={{ ...th, ...right }}>Sklad</th><th style={{ ...th, ...right }}>Prodáno 90 d</th><th style={{ ...th, ...right }}>Prodáno celkem</th></tr></thead>
          <tbody>{d.sizes.map((s) => (
            <tr key={s.variant_id} style={{ background: s.stock === 0 && s.units_total > 0 ? "#fdecea" : undefined }}>
              <td style={td}>{s.size}</td><td style={td}>{s.colour ?? "—"}</td>
              <td style={{ ...td, ...right }}>{num(s.stock)}</td><td style={{ ...td, ...right }}>{num(s.units_90d)}</td><td style={{ ...td, ...right }}>{num(s.units_total)}</td>
            </tr>
          ))}</tbody>
        </table>
        <p style={{ color: "#666", fontSize: 12 }}>Červeně: velikost je na nule, ale prodávala se.</p>
      </Section>
    </main>
  );
}
