import { useState } from 'react';
import { ArrowRight, ArrowUpRight, Camera, ChevronRight, Clock3, Film, Grid2X2, List, Play, Plus, Search, SlidersHorizontal, Target, Upload, X } from 'lucide-react';
import type { Session, Settings } from './types';
import { asset } from './api';
import { BallMark, capitalize, clock, dateLabel, EmptyState, Modal, Status } from './components';
import { sessionTotals, strokeColors, strokes } from './tennis';

function SessionTile({ session, onOpen, featured = false }: { session: Session; onOpen: () => void; featured?: boolean }) {
  const shots = session.report?.shots || [];
  const poster = asset(session.media?.['poster.jpg']);
  return <button className={`sv-session ${featured ? 'sv-featured' : ''}`} onClick={onOpen} aria-label={`Open ${session.title}`}>
    <div className="sv-session-image">
      <img src={poster || '/court.svg'} alt={poster ? `${session.title} video preview` : 'Illustrated tennis court preview'}/>
      <div className="sv-image-top"><span className="sv-type"><BallMark small/>{session.options.session_type || 'Practice'}</span>{session.is_demo && <span className="sv-demo-label">DEMO</span>}</div>
      <span className="sv-play"><Play size={22} fill="currentColor"/></span>
      <div className="sv-image-bottom"><span><Film size={13}/>{session.metadata.height ? `${session.metadata.height}p` : 'VIDEO'}</span><span>{clock(session.metadata.duration)}</span></div>
    </div>
    <div className="sv-session-copy"><div className="sv-session-date">{dateLabel(session.created_at, true)}<span>{session.options.court || 'Tennis court'}</span></div>
      <h3>{session.title}<ChevronRight size={18}/></h3>
      <div className="sv-player"><span className="sv-player-avatar">{session.options.player_name.slice(0, 1)}</span>{session.options.player_name}<span className="sv-shot-count">{shots.length} shots</span></div>
      <div className="sv-stroke-bar" aria-hidden="true">{strokes.map(type => <span key={type} style={{ width: `${shots.length ? shots.filter(shot => shot.type === type).length / shots.length * 100 : 0}%`, background: strokeColors[type] }}/>)}</div>
      <div className="sv-session-footer"><Status session={session}/><span><Clock3 size={12}/>{Math.round(session.metadata.duration / 60)} min</span></div>
    </div>
  </button>;
}

export function SwingLibrary({ sessions, onUpload, onOpen, onRecord }: { sessions: Session[]; onUpload: () => void; onOpen: (id: string) => void; onRecord: () => void }) {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('recent');
  const [layout, setLayout] = useState('grid');
  const [filters, setFilters] = useState(false);
  const [setup, setSetup] = useState(false);
  const totals = sessionTotals(sessions);
  const filtered = sessions.filter(session =>
    `${session.title} ${session.options.player_name} ${session.options.court}`.toLowerCase().includes(query.toLowerCase()) &&
    (type === 'all' || session.options.session_type === type) && (status === 'all' || session.status === status)
  ).sort((a, b) => sort === 'shots' ? (b.report?.shots.length || 0) - (a.report?.shots.length || 0) : (sort === 'oldest' ? 1 : -1) * (Date.parse(a.created_at) - Date.parse(b.created_at)));
  return <div className="sv-library">
    <div className="sv-heading"><div><div className="sv-overline"><span/>YOUR GAME, IN FOCUS</div><h1>Sessions<span>.</span></h1><p>Every shot. Every session. A better game.</p></div><div className="sv-heading-actions"><button className="secondary-button" onClick={onUpload}><Upload size={16}/>Import video</button><button className="primary-button" onClick={onRecord}><Camera size={17}/>Live camera</button></div></div>
    <div className="sv-summary-strip"><div><strong>{totals.sessions}</strong><span>SESSIONS</span></div><div><strong>{totals.shots.toLocaleString()}</strong><span>SHOTS HIT</span></div><div><strong>{(totals.minutes / 60).toFixed(1)}<small> hrs</small></strong><span>TIME ON COURT</span></div><div className="sv-summary-note"><span className="sv-small-court"/><span>Your game.<br/><b>A little clearer.</b></span></div></div>
    {sessions.some(session => session.is_demo) && <div className="sv-sample-note"><span className="sv-demo-label">DEMO</span><span>You’re exploring sample sessions. Import your video to see your own game.</span><button onClick={onUpload}>Get started<ArrowRight size={14}/></button></div>}
    <div className="sv-library-controls"><div className="sv-tabs" aria-label="Session types">{['all', 'Match', 'Practice', 'Drills'].map(value => <button key={value} className={type === value ? 'active' : ''} aria-pressed={type === value} onClick={() => setType(value)}>{value === 'all' ? 'All sessions' : value === 'Match' ? 'Matches' : value}{value === 'all' && <span>{sessions.length}</span>}</button>)}</div><div className="sv-view-controls"><button className={layout === 'grid' ? 'active' : ''} aria-label="Grid view" aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}><Grid2X2 size={17}/></button><button className={layout === 'list' ? 'active' : ''} aria-label="List view" aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><List size={18}/></button></div></div>
    <div className="sv-search-row"><label className="sv-search"><Search size={17}/><input aria-label="Search sessions" placeholder="Search sessions, players or courts" value={query} onChange={event => setQuery(event.target.value)}/>{query && <button aria-label="Clear search" onClick={() => setQuery('')}><X size={15}/></button>}</label><label className="sv-sort"><span className="sr-only">Sort sessions</span><select value={sort} onChange={event => setSort(event.target.value)}><option value="recent">Most recent</option><option value="oldest">Oldest first</option><option value="shots">Most shots</option></select></label><button className={`secondary-button sv-filter-toggle ${status !== 'all' ? 'is-filtered' : ''}`} aria-expanded={filters} onClick={() => setFilters(!filters)}><SlidersHorizontal size={15}/>Filters{status !== 'all' && <span className="good-dot"/>}</button></div>
    {filters && <div className="sv-filter-panel"><label>Processing status<select aria-label="Filter processing status" value={status} onChange={event => setStatus(event.target.value)}><option value="all">All statuses</option><option value="completed">Ready to review</option><option value="queued">Queued</option><option value="processing">Analyzing</option><option value="failed">Needs attention</option></select></label><button className="text-link" onClick={() => { setStatus('all'); setType('all'); setQuery(''); }}>Reset filters</button></div>}
    <div className="sv-results-line"><h2>{type === 'all' ? 'Your sessions' : type === 'Match' ? 'Your matches' : `Your ${type.toLowerCase()} sessions`}</h2><span>{filtered.length} session{filtered.length === 1 ? '' : 's'}</span></div>
    {filtered.length ? <div className={`sv-session-grid ${layout === 'list' ? 'sv-list-view' : ''}`}>{filtered.map(session => <SessionTile key={session.id} session={session} onOpen={() => onOpen(session.id)}/>)}</div> : <section className="panel"><EmptyState title={sessions.length ? 'No sessions found' : 'Your first session starts here'} description={sessions.length ? 'Try another search or reset your filters.' : 'Import a tennis recording to review your shots and technique.'} action={<button className="primary-button" onClick={() => { if (sessions.length) { setQuery(''); setType('all'); setStatus('all'); } else onUpload(); }}>{sessions.length ? 'Reset filters' : 'Import video'}</button>}/></section>}
    <button className="sv-setup-banner" onClick={() => setSetup(true)}><span className="sv-setup-icon"><Camera size={24}/></span><span><strong>A better view. A better analysis.</strong><small>Get your camera in the right spot before your next session.</small></span><span className="sv-setup-link">Camera setup guide<ArrowUpRight size={16}/></span></button>
    <div className="sv-page-end"><BallMark small/><span>MORE COURT TIME. MORE POSSIBILITIES.</span><span>Private by default.</span></div>
    {setup && <Modal title="Set up your court" subtitle="Give every shot the best chance to be measured." onClose={() => setSetup(false)}><div className="sv-setup-guide"><img src="/court.svg" alt="Position the camera behind the baseline with the full court visible"/>{[['01', 'Behind the baseline', 'Center a fixed camera behind the baseline, ideally 3–5 metres high.'], ['02', 'Get the whole picture', 'Keep both players and all court boundaries in the frame. Use 1080p at 60 fps when recording.'], ['03', 'Check before you play', 'Use steady lighting, avoid digital zoom, and confirm permission from everyone in view.']].map(([number, title, description]) => <div key={number}><b>{number}</b><span><h3>{title}</h3><p>{description}</p></span></div>)}</div><div className="modal-actions"><button className="primary-button" onClick={() => { setSetup(false); onRecord(); }}><Camera size={16}/>Open live camera</button></div></Modal>}
  </div>;
}

export function SwingHome({ sessions, settings, onUpload, onOpen, navigate }: { sessions: Session[]; settings: Settings; onUpload: () => void; onOpen: (id: string) => void; navigate: (page: string) => void }) {
  const [goal, setGoal] = useState(() => { try { const saved = Number(localStorage.getItem('courtside-weekly-goal')); return saved >= 1 && saved <= 7 ? saved : 3; } catch { return 3; } });
  const [editing, setEditing] = useState(false);
  const weekStart = new Date(); weekStart.setHours(0, 0, 0, 0); weekStart.setDate(weekStart.getDate() - (weekStart.getDay() + 6) % 7);
  const weekly = sessions.filter(session => session.status === 'completed' && Date.parse(session.created_at) >= weekStart.getTime() && Date.parse(session.created_at) <= Date.now()).length;
  const shots = sessions.filter(session => session.status === 'completed').flatMap(session => session.report?.shots || []);
  return <div className="sv-home"><div className="sv-heading"><div><div className="sv-overline">YOUR TENNIS JOURNEY</div><h1>Let’s play, {settings.display_name}<span>.</span></h1><p>A little more insight. A little better every time.</p></div><button className="primary-button" onClick={onUpload}><Plus size={16}/>New session</button></div>
    <div className="sv-home-grid"><section className="sv-home-feature"><img src="/court.svg" alt="Illustrated tennis court"/><div><span className="sv-overline">SEE YOUR GAME DIFFERENTLY</span><h2>Your next level<br/>starts on court.</h2><p>Record. Review. Return stronger.</p><button className="primary-button" onClick={() => navigate('live')}><Camera size={17}/>Open live camera</button></div></section><section className="panel sv-goal"><Target size={25}/><h2>Your weekly goal</h2><p>Make time for your game.</p><div className="sv-goal-ring" style={{ background: `conic-gradient(var(--accent) ${Math.min(100, weekly / goal * 100)}%, #303033 0)` }}><div><strong>{weekly}<small> / {goal}</small></strong><span>SESSIONS</span></div></div><button className="text-link" onClick={() => setEditing(!editing)}>{editing ? 'Done' : 'Edit goal'}<ChevronRight size={14}/></button>{editing && <label>Sessions per week<select aria-label="Weekly session goal" value={goal} onChange={event => { const value = Number(event.target.value); setGoal(value); try { localStorage.setItem('courtside-weekly-goal', String(value)); } catch { /* The current goal still works when storage is unavailable. */ } }}>{[1, 2, 3, 4, 5, 6, 7].map(value => <option key={value}>{value}</option>)}</select></label>}{sessions.some(session => session.is_demo) && <small className="sv-muted">Sample session activity</small>}</section></div>
    <div className="sv-results-line"><h2>Recent sessions</h2><button className="text-link" onClick={() => navigate('sessions')}>See all<ChevronRight size={16}/></button></div><div className="sv-session-grid">{[...sessions].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 3).map(session => <SessionTile key={session.id} session={session} onOpen={() => onOpen(session.id)}/>)}</div>{!sessions.length && <EmptyState title="Let’s get your first session in" description="Import a recording to start your tennis journey." action={<button className="primary-button" onClick={onUpload}>Import video</button>}/>}
    <section className="panel sv-stroke-summary"><div><span className="sv-overline">KNOW YOUR GAME</span><h2>Every stroke tells a story.</h2><button className="text-link" onClick={() => navigate('progress')}>Explore your stats<ArrowRight size={15}/></button></div><div>{strokes.filter(type => type !== 'unknown').map(type => <div key={type}><span style={{ color: strokeColors[type] }}>●</span><strong>{shots.filter(shot => shot.type === type).length}</strong><small>{capitalize(type)}s</small></div>)}</div></section>
  </div>;
}
