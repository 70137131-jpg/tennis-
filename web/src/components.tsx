import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowUpRight, ChevronRight, Clock3, Play, X, CircleCheck, LoaderCircle, CircleAlert, Video, CalendarDays, Activity } from 'lucide-react';
import type { Session, Shot, ShotType } from './types';
import { asset } from './api';

export const shotColors: Record<ShotType, string> = { forehand: '#467b60', backhand: '#a6bb8b', serve: '#e3bf72', volley: '#90aeb2', unknown: '#c5c8c0' };
export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
export const minutes = (seconds: number) => `${Math.floor(seconds / 60)} min`;
export const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
export const dateLabel = (date: string, full = false) => new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', ...(full ? { year: 'numeric' } : {}) });
export function BallMark({ small = false }: { small?: boolean }) { return <svg width={small ? 22 : 34} height={small ? 22 : 34} viewBox="0 0 34 34" fill="none" aria-hidden="true"><circle cx="17" cy="17" r="14" stroke="currentColor" strokeWidth="1.8"/><path d="M8 6c12 6 12 16 0 22M26 6c-12 6-12 16 0 22" stroke="currentColor" strokeWidth="1.8"/></svg>; }
export function Status({ session }: { session: Session }) { const complete = session.status === 'completed'; return <span className={`status ${session.status}`}>{complete ? <CircleCheck size={12}/> : session.status === 'failed' ? <CircleAlert size={12}/> : <LoaderCircle size={12} className="spin"/>}{complete ? 'Ready to review' : session.status === 'failed' ? 'Needs attention' : session.status === 'queued' ? 'In queue' : `Analyzing · ${session.progress}%`}</span>; }
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) { return <div className="empty-state"><div className="empty-icon"><Video size={27}/></div><h3>{title}</h3><p>{description}</p>{action}</div>; }
export function SessionCard({ session, onOpen, compact = false }: { session: Session; onOpen: () => void; compact?: boolean }) { return <button className={`session-card ${compact ? 'compact' : ''}`} onClick={onOpen}><div className="session-image" style={{ backgroundImage: `url(${asset(session.media?.['poster.jpg']) || '/court.svg'})` }}><span className="session-category">{session.options.session_type || 'Practice'}</span><span className="duration"><Clock3 size={11}/>{minutes(session.metadata.duration)}</span><span className="play-overlay"><Play size={18} fill="currentColor"/></span></div><div className="session-card-body"><div className="session-date">{dateLabel(session.created_at)}<span>·</span>{session.options.court || 'Court 01'}{session.is_demo && <span className="sample-tag">Sample</span>}</div><h3>{session.title}<ArrowUpRight size={17}/></h3><div className="session-card-footer"><span><Activity size={13}/>{session.report?.shots.length ?? '—'} shots</span><Status session={session}/></div></div></button>; }
export function PanelHeading({ eyebrow, title, action }: { eyebrow?: string; title: string; action?: ReactNode }) { return <div className="panel-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h2>{title}</h2></div>{action}</div>; }
export function TextLink({ children, onClick }: { children: ReactNode; onClick: () => void }) { return <button className="text-link" onClick={onClick}>{children}<ChevronRight size={15}/></button>; }
export function Modal({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null); const closeRef = useRef(onClose); closeRef.current = onClose;
  useEffect(() => { const previous = document.activeElement as HTMLElement; const previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; ref.current?.focus();
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); if (e.key === 'Tab') { const controls = ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]'); if (!controls?.length) return; const first = controls[0], last = controls[controls.length - 1]; if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } } };
    document.addEventListener('keydown', handler); return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', handler); previous?.focus(); }; }, []);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}><div className={`modal ${wide ? 'modal-wide' : ''}`} ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-heading"><div><h2 id="modal-title">{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={20}/></button></div>{children}</div></div>;
}
export function scoreFor(shots: Shot[], metric = 'knee_angle') { const values = shots.flatMap(s => s.metrics.filter(m => m.name === metric && m.measurable && m.target && m.value !== null)); return values.length ? Math.round(values.filter(m => m.value! >= m.target![0] && m.value! <= m.target![1]).length / values.length * 100) : null; }
export function TrendChart({ sessions, shotType = 'all', metric = 'knee_angle' }: { sessions: Session[]; shotType?: string; metric?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const rows = [...sessions].reverse().slice(-8).map(s => ({ name: dateLabel(s.created_at), value: scoreFor(s.report?.shots.filter(shot => shotType === 'all' || shot.type === shotType) || [], metric) })).filter(r => r.value !== null);
  const hasRows = rows.length > 0;
  useEffect(() => {
    if (!hasRows || !container.current || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.max(180, Math.round(entry.contentRect.width)));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, [hasRows]);
  if (!rows.length) return <EmptyState title="Your progress starts here" description="Upload a session to see how your measured technique changes over time."/>;
  const right = width - 24;
  const coords = rows.map((r, i) => [44 + i / Math.max(1, rows.length - 1) * (right - 44), 175 - r.value! / 100 * 145]);
  const labeled = new Set([0, rows.length - 1]);
  let previousLabel = coords[0][0];
  for (let i = 1; i < rows.length - 1; i++) {
    if (coords[i][0] - previousLabel >= 60 && right - coords[i][0] >= 60) {
      labeled.add(i);
      previousLabel = coords[i][0];
    }
  }
  const path = coords.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
  return <div className="chart-wrapper" ref={container}><svg viewBox={`0 0 ${width} 221`} className="trend-chart" role="img" aria-label={`Sessions within the ${metric.replaceAll('_', ' ')} target: ${rows.map(r => `${r.name}: ${r.value}%`).join(', ')}`}><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#82a884" stopOpacity=".20"/><stop offset="100%" stopColor="#82a884" stopOpacity="0"/></linearGradient></defs>{[0,25,50,75,100].map(v => <g key={v}><line x1="44" y1={175-v/100*145} x2={right} y2={175-v/100*145} stroke="#eceee8" strokeDasharray="4 5"/><text x="35" y={179-v/100*145} textAnchor="end" fill="#8a9089" fontSize="13">{v}%</text></g>)}<path d={`${path} L${coords.at(-1)![0]},175 L${coords[0][0]},175 Z`} fill="url(#chart-fill)"/><path d={path} fill="none" stroke="#3e7758" strokeWidth="2.6" strokeLinejoin="round"/>{coords.map((p,i) => <g key={i}><circle cx={p[0]} cy={p[1]} r="4" fill="#fff" stroke="#3e7758" strokeWidth="2"/><title>{rows[i].name}: {rows[i].value}%</title>{labeled.has(i)&&<text x={p[0]} y="208" textAnchor="middle" fill="#8a9089" fontSize="13">{rows[i].name}</text>}</g>)}</svg></div>;
}
export function CalendarStrip({ sessions }: { sessions: Session[] }) { const days = Array.from({ length: 7 }, (_, i) => { const date = new Date(); date.setDate(date.getDate() - (date.getDay() + 6) % 7 + i); return date; }); return <div className="calendar-strip">{days.map((day,i) => { const count = sessions.filter(s => new Date(s.created_at).toDateString() === day.toDateString()).length; const today = day.toDateString() === new Date().toDateString(); return <div key={i} className={`calendar-day ${today ? 'today' : ''}`}><span>{day.toLocaleDateString('en-US', { weekday: 'narrow' })}</span><strong>{day.getDate()}</strong><span className={`activity-dot ${count ? 'has-activity' : ''}`}/></div>; })}</div>; }
export function PageTitle({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: ReactNode }) { return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{children}</div>; }
export function MetaLine({ session }: { session: Session }) { return <div className="meta-line"><span><CalendarDays size={14}/>{dateLabel(session.created_at, true)}</span><span><Clock3 size={14}/>{minutes(session.metadata.duration)}</span><span><Video size={14}/>{session.metadata.height}p · {Math.round(session.metadata.fps)} fps</span></div>; }
