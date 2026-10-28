// Step 3 as a decision diagram: the questions the Judge asks, in order. The open row's path lights up.
export function routeOf(row) {
  if (!row) return null;
  const why = row.facts.map(f => f.why).join(' | ');
  if (!row.facts.length) return 'nofact';
  if (why.includes('stale')) return 'stale';
  if (why.includes('premature')) return 'premature';
  if (why.includes('hype')) return 'hype';
  if (why.includes('bound')) return 'bound';
  if (why.includes('matches') || why.includes('read as')) return 'match';
  return 'thin';
}

const Q = [
  { id: 'q1', y: 14, text: 'Found a fact to check?', no: 'nofact', noText: 'No: lean true (most are)' },
  { id: 'q2', y: 92, text: 'Exact value, not “over 5,000”?', no: 'bound', noText: 'No: a bound, lean false' },
  { id: 'q3', y: 170, text: 'Other sources on this fact?', no: 'thin', noText: 'No: too little evidence' },
  { id: 'q4', y: 248, text: 'Same value the timeline holds that day?', no: null, yes: 'match', yesText: 'Yes: it holds' },
];
const OUTCOMES = [
  { id: 'stale', x: 18, label: 'Stale', sub: 'seen before, then changed' },
  { id: 'premature', x: 166, label: 'Premature', sub: 'only true later' },
  { id: 'hype', x: 314, label: 'Hype', sub: 'no source backs it' },
];

export default function JudgeFlow({ route }) {
  const on = id => route === id;
  const passed = qi => {
    // which questions the route got past with a "yes"
    const order = { nofact: 0, bound: 1, thin: 2, match: 3, stale: 4, premature: 4, hype: 4 };
    return route && order[route] > qi;
  };
  return (
    <figure className="flow">
      <svg viewBox="0 0 470 430" role="img"
        aria-label="The Judge asks: found a fact? exact value? other sources? same value as the timeline? If not: stale, premature or hype. A trained tree model then weighs the evidence into a confidence.">
        {Q.map((q, i) => (
          <g key={q.id}>
            <rect x="18" y={q.y} width="270" height="44" rx="12" className={'fq' + (passed(i) || (q.yes && on(q.yes)) ? ' lit' : '')} />
            <text x="34" y={q.y + 27} className="fq-text">{q.text}</text>
            {i < Q.length - 1 && (
              <path d={`M153,${q.y + 44} V${Q[i + 1].y}`} className={'fe' + (passed(i) ? ' lit' : '')} />
            )}
            {q.no && (
              <g className={'fo' + (on(q.no) ? ' lit' : '')}>
                <path d={`M288,${q.y + 22} H310`} className="fe" />
                <rect x="310" y={q.y + 4} width="150" height="36" rx="10" />
                <text x="322" y={q.y + 26} className="fo-text">{q.noText}</text>
              </g>
            )}
            {q.yes && (
              <g className={'fo good' + (on(q.yes) ? ' lit' : '')}>
                <path d={`M288,${q.y + 22} H310`} className="fe" />
                <rect x="310" y={q.y + 4} width="150" height="36" rx="10" />
                <text x="322" y={q.y + 26} className="fo-text">{q.yesText}</text>
              </g>
            )}
          </g>
        ))}
        <path d="M153,292 V318" className={'fe' + (['stale', 'premature', 'hype'].includes(route) ? ' lit' : '')} />
        <text x="164" y="310" className="fe-label">No: why not?</text>
        {OUTCOMES.map(o => (
          <g key={o.id} className={'fo bad' + (on(o.id) ? ' lit' : '')}>
            <rect x={o.x} y="320" width="138" height="48" rx="12" />
            <text x={o.x + 12} y="341" className="fo-title">{o.label}</text>
            <text x={o.x + 12} y="358" className="fo-text">{o.sub}</text>
          </g>
        ))}
        <rect x="18" y="384" width="434" height="40" rx="12" className="fq score" />
        <text x="34" y="409" className="fq-text">Then a tree model weighs the evidence into a confidence</text>
      </svg>
      <figcaption>
        {route ? 'The highlighted path is how the Judge read the open row.' : 'Open a row to see the path it took.'}
      </figcaption>
    </figure>
  );
}
