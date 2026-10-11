import { ApiError, request } from './api';
import type { MatchState } from './MatchCenter';

interface WatchCommand { action: 'state' | 'point' | 'undo'; request_id?: string; revision?: number; winner?: 0 | 1; session_id?: string }
export async function handleWatchCommand(command: WatchCommand) {
  try {
    const session = window.location.hash.match(/^#session\/([a-f0-9]{24}|demo-[1-6])$/)?.[1];
    if (!session) throw new ApiError('Open a session in the iPhone app first.', 409);
    if (!command || !['state', 'point', 'undo'].includes(command.action)) throw new ApiError('Unsupported Watch command.', 400);
    if (command.action !== 'state' && command.session_id !== session) throw new ApiError('The iPhone session changed. Refresh the Watch score.', 409);
    const state = command.action === 'state'
      ? await request<MatchState>(`/sessions/${session}/match`)
      : await request<MatchState>(`/sessions/${session}/match/actions`, { method: 'POST', body: JSON.stringify({ action: command.action, request_id: command.request_id, revision: command.revision, ...(command.action === 'point' ? { winner: command.winner } : {}) }) });
    return { ok: true, state: { session_id: state.session_id, revision: state.revision, config: state.config, score: state.score } };
  } catch (error) {
    return { ok: false, error: (error as Error).message, status: error instanceof ApiError ? error.status : 0 };
  }
}

declare global { interface Window { courtsideWatch: typeof handleWatchCommand } }
// Runs in the signed-in iPhone web view. The native bridge never receives access tokens.
window.courtsideWatch = handleWatchCommand;
