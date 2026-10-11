import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MatchCenter, { type MatchState } from './MatchCenter';
import { demoSessions } from './demo';
import { ApiError, request } from './api';
import { handleWatchCommand } from './watchBridge';

vi.mock('./api', async importOriginal => ({ ...await importOriginal<typeof import('./api')>(), request: vi.fn() }));
const mockedRequest = vi.mocked(request);
const initial = (): MatchState => ({
  session_id: 'demo-1', revision: 0, config: { players: ['Ali', 'Opponent'], best_of: 3, first_server: 0, no_ad: false }, events: [],
  score: { points: ['0', '0'], games: [0, 0], sets: [0, 0], set_history: [], server: 0, tiebreak: false, winner: null, points_played: 0 },
  rallies: [{ id: 'rally-0001', start: 0, end: 2, shots: 4, shot_types: ['forehand'], confidence: 0.9 }], line_reviews: [],
});

beforeEach(() => { vi.clearAllMocks(); window.location.hash = '#session/demo-1'; });

describe('match review', () => {
  it('scores, locks configuration, and undoes a confirmed point', async () => {
    const state = initial();
    mockedRequest.mockResolvedValueOnce(state).mockResolvedValueOnce({ ...state, revision: 1, events: [{ id: 'point-1', winner: 0, rally_id: null }], score: { ...state.score, points: ['15', '0'], points_played: 1 } }).mockResolvedValueOnce({ ...state, revision: 2 });
    render(<MatchCenter session={demoSessions()[0]} online/>);
    fireEvent.click(await screen.findByRole('button', { name: 'Point to Ali' }));
    await screen.findByText('15');
    expect((screen.getByRole('button', { name: 'Match settings' }) as HTMLButtonElement).disabled).toBe(true);
    const posted = JSON.parse(mockedRequest.mock.calls[1][1]!.body as string);
    expect(posted).toMatchObject({ revision: 0, action: 'point', winner: 0 });
    expect(posted.request_id).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Undo point' }));
    await waitFor(() => expect((screen.getByRole('button', { name: 'Undo point' }) as HTMLButtonElement).disabled).toBe(true));
    expect(JSON.parse(mockedRequest.mock.calls[2][1]!.body as string)).toMatchObject({ revision: 1, action: 'undo' });
  });

  it('refreshes conflicts without adding a point locally', async () => {
    const state = initial();
    mockedRequest.mockResolvedValueOnce(state).mockRejectedValueOnce(new ApiError('Score changed on another device', 409)).mockResolvedValueOnce({ ...state, revision: 3 });
    render(<MatchCenter session={demoSessions()[0]} online/>);
    fireEvent.click(await screen.findByRole('button', { name: 'Point to Ali' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Score changed'));
    expect(screen.queryByText('15')).toBeNull();
    await waitFor(() => expect(mockedRequest).toHaveBeenCalledTimes(3));
  });

  it('exports the selected rallies and filters without changing selection', async () => {
    mockedRequest.mockResolvedValueOnce(initial()).mockResolvedValueOnce({ id: 'export-1', status: 'completed', url: '/api/media/test/highlight.mp4?signature=abc' });
    render(<MatchCenter session={demoSessions()[0]} online/>);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select rally-0001' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter rallies by stroke' }), { target: { value: 'serve' } });
    expect(screen.getByText('No rally candidates')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Export highlights' }));
    expect((await screen.findByRole('link', { name: 'Download highlight video' })).getAttribute('href')).toContain('signature=abc');
    expect(JSON.parse(mockedRequest.mock.calls[1][1]!.body as string)).toEqual({ rally_ids: ['rally-0001'] });
  });

  it('requires ground contact confirmation before requesting a calibrated line estimate', async () => {
    const session = demoSessions()[0];
    session.options.court_corners = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]];
    session.media = { [session.report!.annotated_video]: '/test.mp4' };
    mockedRequest.mockResolvedValueOnce(initial()).mockResolvedValueOnce({ candidates: [] }).mockResolvedValueOnce({ id: 'review-1', time: 0, call: 'uncertain', uncertainty_m: 0.12 }).mockResolvedValueOnce(initial());
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    const { container } = render(<MatchCenter session={session} online/>);
    await screen.findByText('Every point counts.');
    const video = container.querySelector('video')!;
    Object.defineProperty(video, 'duration', { value: 3 });
    fireEvent.loadedMetadata(video);
    fireEvent.click(screen.getByRole('button', { name: 'Line review' }));
    const overlay = await screen.findByRole('button', { name: 'Mark ball ground contact on video' });
    vi.spyOn(overlay, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, top: 0, left: 0, width: 100, height: 100, bottom: 100, right: 100, toJSON: () => ({}) });
    fireEvent.keyDown(overlay, { key: 'ArrowRight' });
    fireEvent.keyDown(overlay, { key: 'ArrowLeft' });
    fireEvent.click(overlay, { detail: 0 });
    expect((screen.getByRole('button', { name: 'Estimate line call' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: /I can see the ball touching/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Estimate line call' }));
    await screen.findByText('Too close to call');
    expect(JSON.parse(mockedRequest.mock.calls[2][1]!.body as string)).toMatchObject({ time: 0, x: 0.5, y: 0.5, ground_contact_confirmed: true, corners: session.options.court_corners });
    fireEvent.click(screen.getByRole('button', { name: 'Next frame' }));
    expect((screen.getByRole('button', { name: 'Estimate line call' }) as HTMLButtonElement).disabled).toBe(true);
    vi.restoreAllMocks();
  });

  it('shows an offline state without inventing match results', () => {
    render(<MatchCenter session={demoSessions()[0]} online={false}/>);
    expect(screen.getByText('Connect to your local server')).toBeTruthy();
    expect(mockedRequest).not.toHaveBeenCalled();
  });
});

describe('Watch bridge', () => {
  it('returns only score information and forwards stable request IDs', async () => {
    mockedRequest.mockResolvedValue(initial());
    const result = await handleWatchCommand({ action: 'state' });
    expect(result.state).not.toHaveProperty('events');
    expect(result.state).not.toHaveProperty('rallies');
    const command = { action: 'point' as const, winner: 1 as const, session_id: 'demo-1', request_id: 'watch-retry-01', revision: 0 };
    await handleWatchCommand(command);
    await handleWatchCommand(command);
    expect(mockedRequest.mock.calls[1]).toEqual(mockedRequest.mock.calls[2]);
    expect(JSON.parse(mockedRequest.mock.calls[1][1]!.body as string)).toEqual({ action: 'point', winner: 1, request_id: 'watch-retry-01', revision: 0 });
  });

  it('rejects closed or changed sessions before touching the API', async () => {
    window.location.hash = '#sessions';
    expect(await handleWatchCommand({ action: 'state' })).toMatchObject({ ok: false, status: 409 });
    window.location.hash = '#session/demo-2';
    expect(await handleWatchCommand({ action: 'undo', session_id: 'demo-1' })).toMatchObject({ ok: false, status: 409 });
    expect(mockedRequest).not.toHaveBeenCalled();
  });

  it('distinguishes known rejections from retryable connection failures', async () => {
    mockedRequest.mockRejectedValueOnce(new ApiError('Conflict', 409)).mockRejectedValueOnce(new Error('Connection lost'));
    expect(await handleWatchCommand({ action: 'state' })).toMatchObject({ ok: false, status: 409 });
    expect(await handleWatchCommand({ action: 'state' })).toMatchObject({ ok: false, status: 0 });
  });
});
