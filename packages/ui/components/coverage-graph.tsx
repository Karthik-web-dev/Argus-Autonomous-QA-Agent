export function CoverageGraph({ values }: { values: number[] }) {
  return <div aria-label="Coverage by run" style={{ display: "flex", alignItems: "end", gap: 6, height: 100 }}>
    {values.map((value, index) => <div key={index} title={`${value}%`} style={{ height: `${Math.max(2, Math.min(100, value))}%`, flex: 1, background: "#83e3c2", borderRadius: 4 }} />)}
  </div>;
}
