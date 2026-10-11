import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SwingHome, SwingLibrary } from './SwingViews';
import ShotInsights from './ShotInsights';
import SessionReport from './SessionReport';
import { defaultSettings, demoSessions } from './demo';
import { positionedShots, sessionTotals } from './tennis';

const libraryProps = () => ({ sessions: demoSessions(), onOpen: vi.fn(), onUpload: vi.fn(), onRecord: vi.fn() });

describe('tennis session experience', () => {
  it('combines stroke-session filters with search and resets an empty result', () => {
    const props = libraryProps();
    render(<SwingLibrary {...props}/>);
    expect(screen.getAllByRole('button', { name: /^Open (?!live)/ })).toHaveLength(6);
    fireEvent.click(screen.getByRole('button', { name: 'Matches' }));
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Open Match day' }));
    expect(props.onOpen).toHaveBeenCalledWith('demo-4');
    fireEvent.change(screen.getByRole('textbox', { name: 'Search sessions' }), { target: { value: 'missing' } });
    expect(screen.getByText('No sessions found')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }));
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(6);
  });

  it('sorts recordings and filters processing states without losing the data', () => {
    const props = libraryProps();
    props.sessions[0].status = 'processing';
    render(<SwingLibrary {...props}/>);
    fireEvent.change(screen.getByRole('combobox', { name: 'Sort sessions' }), { target: { value: 'shots' } });
    expect(screen.getAllByRole('button', { name: /^Open / })[0].getAttribute('aria-label')).toBe('Open Match day');
    fireEvent.click(screen.getByRole('button', { name: 'Filters' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter processing status' }), { target: { value: 'processing' } });
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Open Baseline practice' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'List view' }));
    expect(screen.getByRole('button', { name: 'List view' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('connects import, camera and setup guide actions', () => {
    const props = libraryProps();
    render(<SwingLibrary {...props}/>);
    fireEvent.click(screen.getByRole('button', { name: 'Import video' }));
    expect(props.onUpload).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: 'Live camera' }));
    expect(props.onRecord).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: /Camera setup guide/ }));
    const dialog = screen.getByRole('dialog', { name: 'Set up your court' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Open live camera' }));
    expect(props.onRecord).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('counts only completed analysis in the overview and persists weekly goals', () => {
    const sessions = demoSessions();
    sessions[0].status = 'failed';
    expect(sessionTotals(sessions).sessions).toBe(5);
    expect(sessionTotals(sessions).shots).toBe(236);
    const { unmount } = render(<SwingHome sessions={sessions} settings={defaultSettings} onOpen={vi.fn()} onUpload={vi.fn()} navigate={vi.fn()}/>);
    fireEvent.click(screen.getByRole('button', { name: 'Edit goal' }));
    fireEvent.change(screen.getByLabelText('Weekly session goal'), { target: { value: '5' } });
    expect(localStorage.getItem('courtside-weekly-goal')).toBe('5');
    unmount();
    render(<SwingHome sessions={[]} settings={defaultSettings} onOpen={vi.fn()} onUpload={vi.fn()} navigate={vi.fn()}/>);
    fireEvent.click(screen.getByRole('button', { name: 'Edit goal' }));
    expect((screen.getByLabelText('Weekly session goal') as HTMLSelectElement).value).toBe('5');
  });

  it('filters court positions by player and stroke without synthesizing missing points', () => {
    const base = demoSessions()[0].report!.shots[0];
    const shots = [
      { ...base, id: 'near', type: 'forehand' as const, court_position: [4, 20] },
      { ...base, id: 'far', type: 'backhand' as const, player_id: 'player-far', court_position: [2, 5] },
      { ...base, id: 'missing', court_position: null },
      { ...base, id: 'invalid', court_position: [NaN, 3] },
    ];
    expect(positionedShots(shots)).toHaveLength(2);
    render(<ShotInsights shots={shots} view="court" demo={false}/>);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('2 calibrated shots');
    fireEvent.click(screen.getByRole('button', { name: 'Backhand' }));
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('1 calibrated shots');
    fireEvent.change(screen.getByLabelText('Statistics player'), { target: { value: 'player-near' } });
    expect(screen.getByText('No calibrated positions')).toBeTruthy();
    expect(screen.getByText(/not ball bounces/)).toBeTruthy();
  });

  it('opens report tabs, preserves video controls, and does not invent real clips', () => {
    const session = { ...demoSessions()[0], is_demo: false };
    render(<SessionReport session={session} online={false} onBack={vi.fn()} onDelete={vi.fn()} notify={vi.fn()} refresh={vi.fn()}/>);
    expect(screen.getByText('Video unavailable')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Play illustration' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Playback speed'), { target: { value: '0.5' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Shot stats' }));
    expect(screen.getByRole('tabpanel', { name: 'Shot stats' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Serve' }));
    expect(screen.getByText('Technique averages')).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Shot stats' }), { key: 'ArrowRight' });
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Court positions' }));
    expect(screen.getByText('No calibrated positions')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Video & shots' }));
    expect((screen.getByLabelText('Playback speed') as HTMLSelectElement).value).toBe('0.5');
  });
});

describe('report playback', () => {
  it('applies playback speed to actual media and restores it when metadata loads', () => {
    const session = demoSessions()[0];
    session.is_demo = false;
    const shot = session.report!.shots[0];
    shot.clip = 'shot.mp4';
    session.media = { 'shot.mp4': '/test-media/shot.mp4', [session.report!.annotated_video]: '/test-media/session.mp4' };
    const { container } = render(<SessionReport session={session} online={false} onBack={vi.fn()} onDelete={vi.fn()} notify={vi.fn()} refresh={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText('Playback speed'), { target: { value: '0.5' } });
    expect(container.querySelector('video')!.playbackRate).toBe(0.5);
    fireEvent.click(screen.getByRole('button', { name: 'Full session' }));
    const video = container.querySelector('video')!;
    fireEvent.loadedMetadata(video);
    expect(video.playbackRate).toBe(0.5);
    expect(video.currentTime).toBe(shot.contact);
  });

  it('does not leave an unrelated shot selected when a filter has no matches', () => {
    const session = demoSessions()[0];
    session.report!.shots = session.report!.shots.filter(shot => shot.type === 'forehand');
    render(<SessionReport session={session} online={false} onBack={vi.fn()} onDelete={vi.fn()} notify={vi.fn()} refresh={vi.fn()}/>);
    fireEvent.click(screen.getByRole('button', { name: 'Serve' }));
    expect(screen.getByText('No shots here yet')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Play illustration' })).toBeNull();
  });
});
