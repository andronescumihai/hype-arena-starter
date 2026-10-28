import { useEffect, useMemo, useRef, useState } from 'react';
import MicroSlats from './bits/MicroSlats.jsx';
import ParticleText from './bits/ParticleText.jsx';
import StrokeText from './bits/StrokeText.jsx';
import SlingButton from './bits/SlingButton.jsx';
import Architecture from './Architecture.jsx';
import Timeline from './Timeline.jsx';

const ORDER = ['extractor', 'historian', 'judge', 'writer', 'referee'];
const TYPE_NAMES = { fact: 'Fact', compare: 'Compare', change: 'Change', at_event: 'At an event', relation: 'Relation' };

function toCsv(rows) {
  const q = s => (/[",\n]/.test(s) ? `"${String(s).replace(/"/g, '""')}"` : s);
  return ['id,text,date', ...rows.map(r => [r.id, r.text, r.date].map(q).join(','))].join('\n');
}

function Verdict({ label, confidence }) {
  return (
    <span className={`verdict v-${label}`}>
      <b>{label === 'false' ? 'Hype' : label === 'true' ? 'Truth' : 'Unsure'}</b>
      <span className="conf" aria-label={`confidence ${Math.round(confidence * 100)}%`}>
        <span style={{ width: `${Math.round(((confidence - 0.5) / 0.5) * 100)}%` }} />
      </span>
      <small>{Math.round(confidence * 100)}%</small>
    </span>
  );
}

function RowCard({ r, open, onToggle }) {
  return (
    <li className={`row glass ${open ? 'open' : ''}`}>
      <button className="row-head" onClick={onToggle} aria-expanded={open}>
        <time>{r.date}</time>
        <span className="row-text">{r.text}</span>
        <Verdict label={r.label} confidence={r.confidence} />
      </button>
      {r.truth && (
        <p className={`truth-note ${r.truth === r.label ? 'hit' : 'miss'}`}>
          {r.truth === r.label ? 'Matches the known label' : `Known label: ${r.truth}`}
        </p>
      )}
      {open && (
        <div className="row-body">
          {r.facts.length === 0 && <p className="muted">No checkable fact found in this sentence, so the Judge leans on how most sentences turn out.</p>}
          {r.facts.map((f, i) => (
            <div key={i} className="fact">
              <p>
                <strong>{f.subject}</strong> · {f.attribute} · <em>{f.value}</em>
                <span className={`tag t-${f.verdict}`}>{f.why}</span>
              </p>
              <Timeline fact={f} />
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [source, setSource] = useState('');
  const [csv, setCsv] = useState('');
  const [running, setRunning] = useState(false);
  const [active, setActive] = useState(null);
  const [done, setDone] = useState([]);
  const [notes, setNotes] = useState({});
  const [rows, setRows] = useState([]);
  const [claims, setClaims] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [openId, setOpenId] = useState(null);
  const arenaRef = useRef(null);

  useEffect(() => {
    fetch('/api/meta').then(r => r.json()).then(setMeta).catch(() => {});
    loadSample();
  }, []);

  function loadSample() {
    fetch('/api/sample').then(r => r.json()).then(d => {
      setSource(d.source);
      setCsv(toCsv(d.rows));
      window.__truth = Object.fromEntries(d.rows.map(r => [r.id, r.truth || '']));
    });
  }

  function onFile(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then(t => { setCsv(t); setSource(f.name); window.__truth = {}; });
  }

  async function run() {
    if (running) return;
    setError(''); setRows([]); setClaims(null); setSummary(null); setDone([]); setNotes({}); setOpenId(null);
    setRunning(true);
    arenaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const truth = window.__truth || {};
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: csv, truth }),
      });
      if (!res.ok) throw new Error((await res.json()).error || 'The run failed.');
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      let last = null;
      for (;;) {
        const { value, done: end } = await reader.read();
        if (end) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const e = JSON.parse(line);
          if (e.type === 'stage') {
            if (last) setDone(d => [...d, last]);
            last = e.agent;
            setActive(e.agent);
            setNotes(n => ({ ...n, [e.agent]: e.note }));
          } else if (e.type === 'row') {
            const t = truth[e.id];
            setRows(rs => [...rs, { ...e, truth: e.truth || t || '' }]);
          } else if (e.type === 'claims') {
            setClaims(e);
          } else if (e.type === 'done') {
            setDone(ORDER);
            setActive(null);
            setSummary(e);
          }
        }
      }
    } catch (err) {
      setError(err.message);
      setActive(null);
    } finally {
      setRunning(false);
    }
  }

  const stats = useMemo(() => {
    const t = rows.filter(r => r.label === 'true').length;
    const f = rows.filter(r => r.label === 'false').length;
    const scored = rows.filter(r => r.truth === 'true' || r.truth === 'false');
    const right = scored.filter(r => r.truth === r.label).length;
    const avg = rows.length ? rows.reduce((s, r) => s + r.confidence, 0) / rows.length : 0;
    return { t, f, scored: scored.length, right, avg };
  }, [rows]);

  return (
    <>
      <div className="sea" aria-hidden="true">
        <MicroSlats preset="swell" color="#A855F7" glintColor="#ffffff" backgroundColor="#07060B"
          slatWidth={10} slatHeight={25} gap={3} roundness={0.75} interactive cursorStrength={1}
          cursorSize={40} swirl={0} trail={1.4} lean={0} intro />
      </div>

      <header className="hero">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <span>Neural Ninjas</span>
          <span className="muted">for QA DNA · NEXXT AI Hackathon</span>
        </div>
        <div className="title" role="heading" aria-level="1" aria-label="Hype or Truth">
          <ParticleText text="Hype or Truth" particleSize={2} density={4} color="#F4F2FF"
            highlightColor="#A855F7" scatter={180} gatherDuration={1600} stagger={420} pointerRepel={40}
            repelRadius={120} idleDrift={0.7} trigger="mount" fontSize="clamp(2.6rem, 9vw, 7.5rem)"
            fontWeight={800} fontFamily="Unbounded, sans-serif" glow />
        </div>
        <p className="lede">
          Hooly's pages contradict each other. Five agents read every sentence, rebuild each fact's timeline
          and decide what holds up, then write a thousand new claims that do.
        </p>

        <section className="console glass" aria-label="Rows to check">
          <div className="console-top">
            <div>
              <h2>Rows to check</h2>
              <p className="muted small">CSV with id, text and date. Loaded: {source || 'nothing yet'}</p>
            </div>
            <div className="console-actions">
              <button className="neu" onClick={loadSample}>Load sample</button>
              <label className="neu">
                Upload CSV
                <input type="file" accept=".csv,text/csv" onChange={onFile} hidden />
              </label>
            </div>
          </div>
          <textarea className="well" value={csv} onChange={e => setCsv(e.target.value)} spellCheck="false"
            aria-label="CSV rows" rows={7} />
          <div className="launch">
            <SlingButton onSend={run} padColor="#F4F2FF" iconColor="#07060B" accentColor="#A855F7"
              wellColor="#151022" bandColor="#6D4BA8" size={56} strokeWidth={3} armAt={48} maxPull={160}
              launchSpeed={2600} recoil={0.2} flight={120} particles={14} spread={60} axis="any" tapSends
              disabled={running} ariaLabel="Run the arena" />
            <div>
              <button className="neu primary" onClick={run} disabled={running}>
                {running ? 'Running…' : 'Run the arena'}
              </button>
              <p className="muted small">or pull the sling and let go</p>
            </div>
          </div>
          {error && <p className="error" role="alert">{error}</p>}
        </section>
      </header>

      <main ref={arenaRef} className="arena">
        <aside className="arch-col glass">
          <h2>How it decides</h2>
          <Architecture active={active} done={done} />
          <ol className="stage-notes">
            {ORDER.filter(a => notes[a]).map(a => (
              <li key={a} className={active === a ? 'now' : ''}><b>{a[0].toUpperCase() + a.slice(1)}</b> {notes[a]}</li>
            ))}
          </ol>
        </aside>

        <section className="feed-col">
          <div className="scoreboard glass">
            {summary && stats.scored ? (
              <StrokeText key={`s${stats.right}`} text={`${stats.right}/${stats.scored}`} strokeColor="#C4B5FD"
                fillColor="#F4F2FF" fontSize={96} fontWeight={800} letterSpacing={-3} trigger="mount" />
            ) : (
              <p className="big">{rows.length ? `${rows.length} judged` : 'Waiting for a run'}</p>
            )}
            <dl>
              <div><dt>Truth</dt><dd className="c-true">{stats.t}</dd></div>
              <div><dt>Hype</dt><dd className="c-false">{stats.f}</dd></div>
              <div><dt>Mean confidence</dt><dd>{rows.length ? `${Math.round(stats.avg * 100)}%` : '–'}</dd></div>
              <div><dt>Run time</dt><dd>{summary ? `${summary.seconds}s` : '–'}</dd></div>
            </dl>
            {summary && stats.scored > 0 && <p className="muted small">Right against the known labels of these rows.</p>}
          </div>

          {rows.length === 0 && !running && (
            <p className="empty">Run the arena to see each sentence judged, with the evidence behind it.</p>
          )}
          <ul className="feed">
            {rows.map(r => (
              <RowCard key={r.id} r={r} open={openId === r.id} onToggle={() => setOpenId(openId === r.id ? null : r.id)} />
            ))}
          </ul>

          {claims && (
            <section className="claims glass">
              <h2>New claims, checked by the Referee</h2>
              <p className="muted">
                {claims.total.toLocaleString()} claims written, every one re-read before it ships.
                {meta && ` ${meta.claims_candidates.toLocaleString()} candidates, ${Object.values(meta.claims_dropped).reduce((a, b) => a + b, 0)} dropped.`}
              </p>
              <div className="type-counts">
                {Object.entries(claims.by_type).map(([t, n]) => <span key={t} className="neu chip">{TYPE_NAMES[t]} <b>{n}</b></span>)}
              </div>
              <ul className="claim-list">
                {claims.items.map(c => (
                  <li key={c.id}><span className="ctype">{TYPE_NAMES[c.type]}</span>{c.text}<small>{Math.round(c.confidence * 100)}%</small></li>
                ))}
              </ul>
            </section>
          )}
        </section>
      </main>

      <footer className="foot">
        {meta && (
          <p>
            Tested on {meta.practice_rows.toLocaleString()} practice rows, labels hidden fold by fold:{' '}
            <b>{(meta.metrics.accuracy_with_anchors * 100).toFixed(1)}%</b> right, against{' '}
            {(meta.metrics.baseline_all_true * 100).toFixed(1)}% for calling everything true.
            {meta.metrics.backtest && (
              <> Claims written from 80% of the rows and checked against all of them:{' '}
                <b>{(meta.metrics.backtest.confirmed / meta.metrics.backtest.claims * 100).toFixed(1)}%</b> confirmed,{' '}
                {meta.metrics.backtest.contradicted} of {meta.metrics.backtest.claims.toLocaleString()} contradicted.</>
            )}
          </p>
        )}
      </footer>
    </>
  );
}
