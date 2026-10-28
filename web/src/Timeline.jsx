// Evidence timeline for one fact: every source over time, the Historian's path, and this sentence.
const KIND = {
  anchor: { r: 4.5, cls: 'pt-anchor', label: 'labelled true' },
  refuted: { r: 4.5, cls: 'pt-refuted', label: 'labelled false' },
  vote: { r: 3.5, cls: 'pt-vote', label: 'other source' },
  self: { r: 7, cls: 'pt-self', label: 'this sentence' },
};

export default function Timeline({ fact }) {
  const { points, path } = fact.timeline;
  if (!points.length) return <p className="muted small">No other source mentions this fact.</p>;
  const values = [...new Set([...path.map(p => p[1]), ...points.map(p => p.value)])];
  const ts = points.map(p => +new Date(p.date));
  const t0 = Math.min(...ts), t1 = Math.max(...ts, t0 + 864e5);
  const W = 560, rowH = 26, padL = 128, padR = 14, top = 10;
  const H = top + values.length * rowH + 26;
  const x = d => padL + ((+new Date(d) - t0) / (t1 - t0)) * (W - padL - padR);
  const y = v => top + values.indexOf(v) * rowH + rowH / 2;
  const steps = path.map(([d, v], i) => (i ? `H${x(d)} V${y(v)}` : `M${x(d)},${y(v)}`)).join(' ');
  const fmt = d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  return (
    <figure className="timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Timeline of ${fact.subject} ${fact.attribute}`}>
        {values.map(v => (
          <g key={v}>
            <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} className="tl-grid" />
            <text x={padL - 10} y={y(v) + 4} textAnchor="end" className="tl-value">{v.length > 16 ? v.slice(0, 15) + '…' : v}</text>
          </g>
        ))}
        <path d={steps} className="tl-path" />
        {points.map((p, i) => {
          const k = KIND[p.kind] || KIND.vote;
          return <circle key={i} cx={x(p.date)} cy={y(p.value)} r={k.r} className={k.cls}><title>{`${p.date}: ${p.value} (${k.label})`}</title></circle>;
        })}
        <text x={padL} y={H - 6} className="tl-axis">{fmt(t0)}</text>
        <text x={W - padR} y={H - 6} textAnchor="end" className="tl-axis">{fmt(t1)}</text>
      </svg>
      <figcaption className="tl-legend">
        <span><i className="dot pt-self" />this sentence</span>
        <span><i className="dot pt-anchor" />labelled true</span>
        <span><i className="dot pt-refuted" />labelled false</span>
        <span><i className="dot pt-vote" />other source</span>
        <span><i className="bar" />what the Historian believes held</span>
      </figcaption>
    </figure>
  );
}
