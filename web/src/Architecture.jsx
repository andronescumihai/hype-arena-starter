// The system's architecture as a live diagram: each agent lights up while it works.
const NODES = [
  { id: 'extractor', x: 40, y: 40, title: 'Extractor', line: 'Reads facts from each sentence' },
  { id: 'historian', x: 40, y: 150, title: 'Historian', line: 'One timeline per fact' },
  { id: 'judge', x: 40, y: 260, title: 'Judge', line: 'Stale, premature or hype?' },
  { id: 'writer', x: 250, y: 150, title: 'Writer', line: 'Claims from what holds' },
  { id: 'referee', x: 250, y: 260, title: 'Referee', line: 'Re-reads, drops the unsafe' },
];
const EDGES = [
  ['extractor', 'historian'],
  ['historian', 'judge'],
  ['historian', 'writer'],
  ['writer', 'referee'],
];
const W = 190;
const H = 74;

export default function Architecture({ active, done }) {
  const at = id => NODES.find(n => n.id === id);
  return (
    <figure className="arch">
      <svg viewBox="0 0 480 380" role="img" aria-label="Architecture: Extractor feeds Historian; Historian feeds Judge and Writer; Writer feeds Referee.">
        <defs>
          <marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
        </defs>
        <text x="40" y="22" className="arch-input">rows + lexicon</text>
        <text x="40" y="364" className="arch-input">labels: true / false + confidence</text>
        <text x="250" y="364" className="arch-input">1,000 checked claims</text>
        {EDGES.map(([a, b]) => {
          const A = at(a), B = at(b);
          const vertical = A.x === B.x;
          const d = vertical
            ? `M${A.x + W / 2},${A.y + H} L${B.x + W / 2},${B.y - 4}`
            : `M${A.x + W},${A.y + H / 2} L${B.x - 4},${B.y + H / 2}`;
          const lit = done.includes(a) && (done.includes(b) || active === b);
          return <path key={a + b} d={d} className={'arch-edge' + (lit ? ' lit' : '')} markerEnd="url(#tip)" />;
        })}
        {NODES.map(n => {
          const state = active === n.id ? 'active' : done.includes(n.id) ? 'done' : 'idle';
          return (
            <g key={n.id} className={`arch-node ${state}`} transform={`translate(${n.x},${n.y})`}>
              <rect width={W} height={H} rx="18" />
              <text x="18" y="30" className="arch-title">{n.title}</text>
              <text x="18" y="52" className="arch-line">{n.line.length > 34 ? n.line.slice(0, 33) + '…' : n.line}</text>
            </g>
          );
        })}
      </svg>
      <figcaption>
        No language model runs here. Every verdict comes from parsed values, timelines and a small tree model
        trained on the practice rows.
      </figcaption>
    </figure>
  );
}
