import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Download, Film, LoaderCircle, Play, RotateCcw, Settings2, Watch } from 'lucide-react';
import { asset, request } from './api';
import { clock, EmptyState, Modal } from './components';
import type { Session } from './types';

export interface Rally { id: string; start: number; end: number; shots: number; shot_types: string[]; confidence: number }
export interface MatchConfig { players: string[]; best_of: 1 | 3 | 5; first_server: 0 | 1; no_ad: boolean }
export interface MatchState {
  session_id: string; revision: number; config: MatchConfig;
  events: { id: string; winner: number; rally_id: string | null }[];
  score: { points: string[]; games: number[]; sets: number[]; set_history: number[][]; server: number; tiebreak: boolean; winner: number | null; points_played: number };
  rallies?: Rally[]; line_reviews?: LineResult[];
}
interface LineResult { id: string; time: number; call: 'in' | 'out' | 'uncertain'; zone: string; uncertainty_m: number; clearance_m: number }
interface ExportState { id: string; status: 'processing' | 'completed' | 'failed'; url?: string; error?: string }

export default function MatchCenter({ session, online }: { session: Session; online: boolean }) {
  const [match, setMatch] = useState<MatchState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState<MatchConfig | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [stroke, setStroke] = useState('all');
  const [sort, setSort] = useState('time');
  const [current, setCurrent] = useState<Rally | null>(null);
  const [exportJob, setExportJob] = useState<ExportState | null>(null);
  const [watchHelp, setWatchHelp] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoError, setVideoError] = useState('');
  const [lineMode, setLineMode] = useState(false);
  const [corners, setCorners] = useState<number[][]>(session.options.court_corners || []);
  const [calibrating, setCalibrating] = useState(false);
  const [point, setPoint] = useState<number[] | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [zone, setZone] = useState('singles');
  const [uncertainty, setUncertainty] = useState('0.12');
  const [lineResult, setLineResult] = useState<LineResult | null>(null);
  const [candidates, setCandidates] = useState<{ time: number }[]>([]);
  const source = asset(session.media?.[session.report?.annotated_video || '']);
  const prefix = `/sessions/${session.id}`;
  const refresh = useCallback(async () => {
    const value = await request<MatchState>(`${prefix}/match`);
    setMatch(previous => previous && previous.revision > value.revision ? previous : value);
  }, [prefix]);
  useEffect(() => {
    if (!online) return;
    let cancelled = false;
    const load = () => request<MatchState>(`${prefix}/match`).then(value => { if (!cancelled) { setMatch(previous => previous && previous.revision > value.revision ? previous : value); } }).catch(reason => { if (!cancelled) setError((reason as Error).message); });
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [online, prefix]);
  useEffect(() => {
    if (!exportJob || exportJob.status !== 'processing') return;
    let cancelled = false;
    const timer = setInterval(() => {
      void request<ExportState>(`${prefix}/highlights/${exportJob.id}`).then(value => { if (!cancelled) setExportJob(value); }).catch(reason => { if (!cancelled) { setError((reason as Error).message); } });
    }, 1500);
    return () => { cancelled = true; clearInterval(timer); };
  }, [prefix, exportJob]);
  const act = async (action: 'point' | 'undo' | 'configure', winner?: number, rallyId?: string) => {
    if (!match || busy) return;
    setBusy(true); setError('');
    try {
      const value = await request<MatchState>(`${prefix}/match/actions`, { method: 'POST', body: JSON.stringify({ request_id: crypto.randomUUID(), revision: match.revision, action, ...(winner !== undefined ? { winner } : {}), ...(rallyId ? { rally_id: rallyId } : {}), ...(action === 'configure' ? { config } : {}) }) });
      setMatch(previous => ({ ...previous, ...value })); setConfig(null);
    } catch (reason) { setError((reason as Error).message); await refresh().catch(() => {}); }
    finally { setBusy(false); }
  };
  const seek = (time: number) => {
    const element = video.current;
    if (!element || !Number.isFinite(element.duration)) return;
    element.pause(); element.currentTime = Math.max(0, Math.min(element.duration - 1 / session.metadata.fps, time));
    setVideoTime(element.currentTime); setPoint(null); setConfirmed(false); setLineResult(null);
  };
  const playRally = (rally: Rally) => {
    if (rally.end > videoDuration + 0.02) { setError('This rally exceeds the available video. Demo timelines are illustrative.'); return; }
    setError(''); setCurrent(rally); setLineMode(false); seek(rally.start);
    void video.current?.play().catch(() => setVideoError('Playback could not start. Use the video controls to try again.'));
  };
  const enterReview = async () => {
    setLineMode(!lineMode); video.current?.pause(); setPoint(null); setConfirmed(false); setCurrent(null);
    if (!lineMode) {
      try { const result = await request<{ candidates: { time: number }[] }>(`${prefix}/bounce-candidates`); setCandidates(result.candidates); }
      catch (reason) { setError((reason as Error).message); }
    }
  };
  const reviewLine = async () => {
    if (!point) return;
    setBusy(true); setError('');
    try {
      const result = await request<LineResult>(`${prefix}/line-reviews`, { method: 'POST', body: JSON.stringify({ time: videoTime, x: point[0], y: point[1], corners, zone, uncertainty_m: Number(uncertainty), ground_contact_confirmed: confirmed }) });
      setLineResult(result); await refresh();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  };
  const exportVideo = async () => {
    setBusy(true); setError(''); setExportJob(null);
    try { setExportJob(await request<ExportState>(`${prefix}/highlights`, { method: 'POST', body: JSON.stringify({ rally_ids: chosen }) })); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  };
  const rallies = (match?.rallies || []).filter(rally => stroke === 'all' || rally.shot_types.includes(stroke)).sort((a, b) => sort === 'longest' ? b.shots - a.shots : a.start - b.start);
  const selectedDuration = (match?.rallies || []).filter(rally => chosen.includes(rally.id)).reduce((total, rally) => total + rally.end - rally.start, 0);
  if (!online) return <section className="panel"><EmptyState title="Connect to your local server" description="Match scores, line reviews, and highlight exports are saved in your private workspace."/></section>;
  return <div className="match-center">
    {error && <div className="form-error" role="alert">{error}<button className="text-link" onClick={() => { setError(''); void refresh().catch(reason => setError((reason as Error).message)); }}>Refresh</button></div>}
    {!match ? <div className="panel page-loading"><LoaderCircle className="spin"/>Loading match tools…</div> : <>
      <section className="panel match-scoreboard"><div className="match-section-heading"><div><span className="sv-overline">{session.is_demo ? 'SAMPLE MATCH' : 'MATCH SCORE'}</span><h2>{match.score.winner === null ? match.score.tiebreak ? 'Tiebreak' : 'Every point counts.' : `${match.config.players[match.score.winner]} wins`}</h2></div><div><button className="icon-button" aria-label="Apple Watch companion" onClick={() => setWatchHelp(true)}><Watch size={20}/></button><button className="icon-button" aria-label="Match settings" disabled={busy || !!match.events.length} onClick={() => setConfig({ ...match.config, players: [...match.config.players] })}><Settings2 size={19}/></button></div></div>
      <div className="score-columns"><span>PLAYER</span><span>SETS</span><span>GAMES</span><span>POINTS</span><span/></div>
      {match.config.players.map((name, index) => <div className="score-player" key={index}><span><i className={match.score.server === index ? 'serving' : ''}/>{name}</span><strong>{match.score.sets[index]}</strong><strong>{match.score.games[index]}</strong><strong className="point-value">{match.score.points[index]}</strong><button className="primary-button" disabled={busy || match.score.winner !== null} onClick={() => void act('point', index)} aria-label={`Point to ${name}`}>+ Point</button></div>)}
      <div className="match-score-footer"><span>{match.score.set_history.length ? match.score.set_history.map((set, index) => `Set ${index + 1}: ${set.join('–')}`).join(' · ') : `Best of ${match.config.best_of} · ${match.config.no_ad ? 'No-ad' : 'Advantage'} scoring`}<small>Scoring advances automatically from confirmed point winners.</small></span><button className="secondary-button" disabled={busy || !match.events.length} onClick={() => void act('undo')}><RotateCcw size={14}/>Undo point</button></div></section>
      <div className="match-workspace"><section className="panel match-video-panel"><div className="match-section-heading"><h2>{lineMode ? 'Review the bounce' : current ? `Rally ${current.id.slice(-4)}` : 'Match replay'}</h2><button className="secondary-button" disabled={!source || !videoDuration} aria-pressed={lineMode} onClick={() => void enterReview()}>{lineMode ? 'Back to replay' : 'Line review'}</button></div>
      {source ? <><div className="match-video-stage"><video ref={video} src={source} controls={!lineMode} playsInline preload="metadata" onError={() => setVideoError('The session video could not load. Refresh to renew the private media link.')} onLoadedMetadata={() => { setVideoDuration(video.current?.duration || 0); setVideoError(''); }} onTimeUpdate={() => { const element = video.current; if (!element) return; setVideoTime(element.currentTime); if (current && element.currentTime >= current.end) element.pause(); }} onSeeked={() => { setPoint(null); setConfirmed(false); setLineResult(null); }}/>
        {lineMode && <button className="line-click-layer" title="Use the arrow keys to move the marker, then Enter to mark the point." onKeyDown={event => { const directions: Record<string, number[]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }; const direction = directions[event.key]; if (!direction) return; event.preventDefault(); setPoint(previous => (previous || [0.5, 0.5]).map((value, index) => Math.max(0, Math.min(1, value + direction[index] * (event.shiftKey ? 0.02 : 0.005))))); setConfirmed(false); setLineResult(null); }} aria-label={calibrating ? 'Mark court corner on video' : 'Mark ball ground contact on video'} onClick={event => { const rect = event.currentTarget.getBoundingClientRect(); const value = event.detail === 0 && event.clientX === 0 && event.clientY === 0 ? point || [0.5, 0.5] : [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height]; if (calibrating) { const next = [...corners, value]; setCorners(next); setPoint(null); if (next.length === 4) setCalibrating(false); } else { setPoint(value); setConfirmed(false); setLineResult(null); } }}>{corners.map((corner, index) => <i className="court-pin" style={{ left: `${corner[0] * 100}%`, top: `${corner[1] * 100}%` }} key={index}>{index + 1}</i>)}{point && <i className="bounce-pin" style={{ left: `${point[0] * 100}%`, top: `${point[1] * 100}%` }}>+</i>}</button>}
      </div><div className="match-replay-controls"><button className="icon-button" aria-label="Previous frame" onClick={() => seek(videoTime - 1 / session.metadata.fps)}><ChevronLeft size={20}/></button><span>{videoTime.toFixed(2)} s / {clock(videoDuration)}</span><button className="icon-button" aria-label="Next frame" onClick={() => seek(videoTime + 1 / session.metadata.fps)}><ChevronRight size={20}/></button><label>Speed<select aria-label="Match playback speed" defaultValue="1" onChange={event => { if (video.current) video.current.playbackRate = Number(event.target.value); }}>{[0.25, 0.5, 1, 2].map(rate => <option key={rate}>{rate}</option>)}</select></label></div>{lineMode && <label className="match-timeline">Review time<input aria-label="Review time" type="range" min="0" max={Math.max(0, videoDuration - 1 / session.metadata.fps)} step={1 / session.metadata.fps} value={videoTime} onChange={event => seek(Number(event.target.value))}/></label>}</> : <EmptyState title="Video unavailable" description="Reconnect or open a session with a playable full video."/>}{videoError && <p role="alert" className="form-error">{videoError}</p>}
      {lineMode && <div className="line-review-tools"><p>Pause at the exact ground-contact frame, then mark the ball’s contact point. Image turns are only review suggestions.</p><button className="secondary-button" onClick={() => { setCorners([]); setCalibrating(true); setPoint(null); setConfirmed(false); setLineResult(null); }}>Calibrate court ({corners.length}/4)</button>{calibrating && <p role="status">Tap {['far left', 'far right', 'near right', 'near left'][corners.length]} singles corner, on the outside edge of the line.</p>}
        <div className="form-grid"><label>Court zone<select value={zone} onChange={event => { setZone(event.target.value); setLineResult(null); }}>{['singles', 'doubles', 'far-left-service', 'far-right-service', 'near-left-service', 'near-right-service'].map(value => <option key={value}>{value}</option>)}</select></label><label>Position uncertainty<select value={uncertainty} onChange={event => { setUncertainty(event.target.value); setLineResult(null); }}><option value="0.12">±12 cm</option><option value="0.25">±25 cm</option><option value="0.5">±50 cm</option></select></label></div>
        <label className="checkbox-label"><input type="checkbox" checked={confirmed} disabled={!point || calibrating} onChange={event => setConfirmed(event.target.checked)}/>I can see the ball touching the ground at this point.</label><button className="primary-button" disabled={busy || !point || !confirmed || corners.length !== 4} onClick={() => void reviewLine()}>Estimate line call</button>{lineResult && <div className={`line-result ${lineResult.call}`} role="status"><strong>{lineResult.call === 'uncertain' ? 'Too close to call' : lineResult.call.toUpperCase()}</strong><span>Provisional estimate · ±{Math.round(lineResult.uncertainty_m * 100)} cm. Review the frame before accepting.</span></div>}
        {candidates.length > 0 && <label>Possible bounce frames<select aria-label="Possible bounce frames" defaultValue="" onChange={event => { if (event.target.value) seek(Number(event.target.value)); }}><option value="">Choose a frame to review</option>{candidates.filter(item => item.time < videoDuration).map(item => <option key={item.time} value={item.time}>{item.time.toFixed(2)} s · unverified</option>)}</select></label>}
        {(match.line_reviews || []).length > 0 && <details><summary>Saved line reviews ({match.line_reviews!.length})</summary>{match.line_reviews!.map(review => <button className="saved-line-review" key={review.id} onClick={() => seek(review.time)}>{review.time.toFixed(2)} s<span>{review.call.toUpperCase()}</span><Play size={12}/></button>)}</details>}
      </div>}</section>
      <section className="panel rally-panel"><div className="match-section-heading"><div><span className="sv-overline">AUTOMATIC RALLY CANDIDATES</span><h2>Keep the good parts.</h2></div><Film size={21}/></div><p>Grouped from shot contacts. Review boundaries before exporting. Score point winners in video order.</p><div className="rally-filters"><select aria-label="Filter rallies by stroke" value={stroke} onChange={event => setStroke(event.target.value)}>{['all', 'forehand', 'backhand', 'serve', 'volley'].map(type => <option value={type} key={type}>{type === 'all' ? 'All strokes' : type}</option>)}</select><select aria-label="Sort rallies" value={sort} onChange={event => setSort(event.target.value)}><option value="time">In order</option><option value="longest">Most shots</option></select></div><div className="rally-list">{rallies.map(rally => { const scored = match.events.find(event => event.rally_id === rally.id); return <div className="rally-row" key={rally.id}><div><input type="checkbox" aria-label={`Select ${rally.id}`} checked={chosen.includes(rally.id)} onChange={event => setChosen(previous => event.target.checked ? [...previous, rally.id] : previous.filter(id => id !== rally.id))}/><button onClick={() => playRally(rally)}><Play size={15}/><span><strong>{clock(rally.start)}–{clock(rally.end)}</strong><small>{rally.shots} shots · {Math.round(rally.confidence * 100)}% contact confidence</small></span></button></div>{scored ? <span className="rally-scored"><Check size={12}/>Point: {match.config.players[scored.winner]}</span> : <div className="rally-winner"><span>Point winner</span>{match.config.players.map((name, index) => <button key={index} disabled={busy || match.score.winner !== null} onClick={() => void act('point', index, rally.id)}>{name}</button>)}</div>}</div>; })}{!rallies.length && <EmptyState title="No rally candidates" description="A completed analysis with detected shot contacts is needed."/>}</div><div className="rally-export"><span>{chosen.length} selected · {clock(selectedDuration)}<small>Up to 50 rallies / 5 minutes. Exports use the processed video.</small></span><button className="primary-button" disabled={busy || !chosen.length || chosen.length > 50 || selectedDuration > 300 || exportJob?.status === 'processing'} onClick={() => void exportVideo()}>{exportJob?.status === 'processing' ? <LoaderCircle className="spin" size={16}/> : <Download size={16}/>}Export highlights</button>{exportJob?.status === 'completed' && exportJob.url && <a className="text-link" href={asset(exportJob.url)} download>Download highlight video<Download size={15}/></a>}{exportJob?.status === 'failed' && <p role="alert">{exportJob.error}</p>}</div></section></div>
    </>}
    {config && <Modal title="Match settings" subtitle="Set these before scoring the first point." onClose={() => setConfig(null)}><form className="match-config form-grid" onSubmit={event => { event.preventDefault(); void act('configure'); }}>{config.players.map((name, index) => <label key={index}>Player {index + 1}<input required maxLength={80} value={name} onChange={event => setConfig({ ...config, players: config.players.map((value, player) => player === index ? event.target.value : value) })}/></label>)}<label>Format<select value={config.best_of} onChange={event => setConfig({ ...config, best_of: Number(event.target.value) as 1 | 3 | 5 })}>{[1, 3, 5].map(value => <option value={value} key={value}>Best of {value}</option>)}</select></label><label>First server<select value={config.first_server} onChange={event => setConfig({ ...config, first_server: Number(event.target.value) as 0 | 1 })}>{config.players.map((name, index) => <option value={index} key={index}>{name}</option>)}</select></label><label className="checkbox-label"><input type="checkbox" checked={config.no_ad} onChange={event => setConfig({ ...config, no_ad: event.target.checked })}/>No-ad scoring</label><button className="primary-button" disabled={busy}>Save match settings</button></form></Modal>}
    {watchHelp && <Modal title="Apple Watch companion" subtitle="Score from your wrist while the iPhone companion is connected." onClose={() => setWatchHelp(false)}><div className="watch-help"><Watch size={35}/><p>Open the Courtside iPhone companion, connect to this server, and open this session. The paired Watch app can fetch the score, award a point, and undo the last point.</p><p>The native companion source is included in this project. Install it with Xcode on a Mac; the browser alone cannot pair with Apple Watch.</p><p>Watch commands use the iPhone’s signed-in workspace. Close the session to stop accepting commands for it.</p></div></Modal>}
  </div>;
}
