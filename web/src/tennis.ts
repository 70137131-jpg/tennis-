import type { Session, Shot } from './types';

export const strokes = ['forehand', 'backhand', 'serve', 'volley', 'unknown'] as const;
export const strokeColors = { forehand: '#30d568', backhand: '#ff9f0a', serve: '#36b9f5', volley: '#ffd60a', unknown: '#98989f' };

export function sessionTotals(sessions: Session[]) {
  const completed = sessions.filter(session => session.status === 'completed');
  return {
    sessions: completed.length,
    shots: completed.reduce((total, session) => total + (session.report?.shots.length || 0), 0),
    minutes: Math.round(completed.reduce((total, session) => total + session.metadata.duration, 0) / 60),
  };
}

// The analyzer reports player contact positions in metres, not ball bounces.
export function positionedShots(shots: Shot[]) {
  return shots.filter(shot => shot.court_position?.length === 2 && shot.court_position.every(Number.isFinite));
}
