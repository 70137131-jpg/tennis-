import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import AccountGate from './AccountGate';
import LivePage from './LivePage';
import ProductionPage from './ProductionPage';
import { configureAccount, request } from './api';
import { defaultSettings, demoSessions } from './demo';
import { TrendChart } from './components';

vi.mock('./api', async importOriginal => ({
  ...await importOriginal<typeof import('./api')>(),
  request: vi.fn(),
}));
const api = vi.mocked(request);
const initialWidth = window.innerWidth;
beforeEach(() => {
  configureAccount(null);
  window.location.hash = '';
  localStorage.clear();
  sessionStorage.clear();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  api.mockImplementation(async path => {
    const values: Record<string, unknown> = {
      '/auth/config': { enabled: false },
      '/health': { model_ready: true },
      '/sessions': demoSessions(),
      '/settings': defaultSettings,
      '/reviews': [],
    };
    return values[path] as never;
  });
});
afterEach(() => {
  configureAccount(null);
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: initialWidth });
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  api.mockReset();
});

describe('account privacy', () => {
  it('keeps the workspace hidden if auth configuration cannot load', async () => {
    api.mockRejectedValueOnce(new Error('Network unavailable'));
    render(<AccountGate><div>Private session feed</div></AccountGate>);
    expect(await screen.findByText(/The sign-in service is unavailable/)).toBeTruthy();
    expect(screen.queryByText('Private session feed')).toBeNull();
  });

  it('shows only the signed-in account’s empty feed', async () => {
    const user = { id: 'player-one', name: 'First Player', email: 'first@example.test', role: 'player', academy_id: 'personal' };
    api.mockImplementation(async path => {
      const values: Record<string, unknown> = {
        '/auth/config': { enabled: true, personal: true, google_enabled: true, setup_available: false },
        '/auth/me': { user, csrf: 'csrf', workspaces: [{ id: user.id, name: user.name, role: user.role }] },
        '/health': { model_ready: true },
        '/sessions': [],
        '/settings': { ...defaultSettings, display_name: 'First' },
        '/reviews': [],
      };
      return values[path] as never;
    });
    render(<AccountGate><App/></AccountGate>);
    expect(await screen.findByText('Connected', {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.getByText(/Your first session starts here/)).toBeTruthy();
    expect(screen.queryByLabelText('Player workspace')).toBeNull();
    expect(screen.queryByText('Demo sessions')).toBeNull();
  });
});

describe('refined workspace flows', () => {
  it('resizes charts without shrinking labels or dropping session data', () => {
    let resize: ResizeObserverCallback;
    const disconnect = vi.fn();
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: ResizeObserverCallback) { resize = callback; }
      observe = vi.fn();
      disconnect = disconnect;
    });
    const { container, rerender } = render(<TrendChart sessions={demoSessions()}/>);
    act(() => resize([{ contentRect: { width: 260 } } as ResizeObserverEntry], {} as ResizeObserver));
    const chart = screen.getByRole('img', { name: /Sessions within the knee angle target/ });
    expect(chart.getAttribute('viewBox')).toBe('0 0 260 221');
    expect(container.querySelectorAll('circle')).toHaveLength(6);
    const dates = [...container.querySelectorAll('text[y="208"]')];
    expect(dates.length).toBeLessThan(6);
    for (let i = 1; i < dates.length; i++) {
      expect(Number(dates[i].getAttribute('x')) - Number(dates[i - 1].getAttribute('x'))).toBeGreaterThan(50);
    }
    act(() => resize([{ contentRect: { width: 600 } } as ResizeObserverEntry], {} as ResizeObserver));
    expect(container.querySelectorAll('text[y="208"]')).toHaveLength(6);
    rerender(<TrendChart sessions={[]}/>);
    expect(screen.getByText('Your progress starts here')).toBeTruthy();
    expect(disconnect).toHaveBeenCalledOnce();
    rerender(<TrendChart sessions={demoSessions()}/>);
    act(() => resize([{ contentRect: { width: 300 } } as ResizeObserverEntry], {} as ResizeObserver));
    expect(screen.getByRole('img').getAttribute('viewBox')).toBe('0 0 300 221');
  });

  it('keeps closed mobile navigation inert and traps focus when opened', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    render(<App/>);
    await screen.findByText('Connected');
    const navigation = document.getElementById('workspace-navigation')!;
    expect(navigation.hasAttribute('inert')).toBe(true);
    const trigger = screen.getByRole('button', { name: 'Open navigation' });
    fireEvent.click(trigger);
    expect(navigation.hasAttribute('inert')).toBe(false);
    expect(document.querySelector('.main-shell')!.hasAttribute('inert')).toBe(true);
    const first = screen.getByRole('button', { name: 'Courtside home' });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(within(navigation).getByRole('button', { name: /Personal workspace/ }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(navigation.hasAttribute('inert')).toBe(true);
    expect(document.activeElement).toBe(trigger);
  });

  it('makes release checks accessible outside the primary game navigation', async () => {
    render(<App/>);
    await screen.findByText('Connected');
    expect(within(screen.getByRole('navigation', { name: 'Main navigation' })).queryByRole('button', { name: 'Release checks' })).toBeNull();
    api.mockRejectedValueOnce(new Error('The local server is offline.'));
    fireEvent.click(screen.getByRole('button', { name: 'Release checks' }));
    expect(await screen.findByText('Release checks are unavailable')).toBeTruthy();
  });

  it('explains unavailable live analysis and blocks incomplete junior permission', () => {
    const { rerender } = render(<LivePage settings={defaultSettings} online={false} modelReady={false}/>);
    expect(screen.getByText('Connect your local server to start analysis.')).toBeTruthy();
    rerender(<LivePage settings={defaultSettings} online={true} modelReady={true}/>);
    fireEvent.click(screen.getByRole('checkbox', { name: /I have permission/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'A junior player is in the camera view.' }));
    expect((screen.getByRole('button', { name: 'Start live feed' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Consenting guardianâ€™s name'), { target: { value: 'Test guardian' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Guardian gave explicit processing consent.' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Junior agrees to live analysis.' }));
    expect((screen.getByRole('button', { name: 'Start live feed' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('recovers from unavailable release checks without showing invented counts', async () => {
    api.mockRejectedValueOnce(new Error('Connection unavailable.'));
    render(<ProductionPage/>);
    expect(screen.getByRole('status').textContent).toContain('Loading');
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText(/0 gates/)).toBeNull();
    api.mockResolvedValueOnce({
      release_ready: false,
      gates: [{ id: 'coach', label: 'Coach review', passed: false, detail: 'Review required' }],
      training: { ready: false, errors: [], splits: {} },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Coach review')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('integrates academy selection and team actions into the main header', async () => {
    const identity = {
      user: { id: 'admin', academy_id: 'academy', name: 'Test administrator', email: 'admin@example.test', role: 'admin' },
      csrf: 'test-csrf',
      workspaces: [{ id: 'admin', name: 'Administrator', role: 'admin' }, { id: 'player', name: 'Test player', role: 'player' }],
    };
    const defaults = api.getMockImplementation()!;
    api.mockImplementation(async (path, options) => {
      if (path === '/auth/config') return { enabled: true, setup_available: false } as never;
      if (path === '/auth/me') return identity as never;
      if (path === '/auth/logout') return { ok: true } as never;
      return defaults(path, options);
    });
    render(<AccountGate><App/></AccountGate>);
    const selector = await screen.findByRole('combobox', { name: 'Player workspace' });
    expect(selector.closest('.topbar')).toBeTruthy();
    expect(document.querySelector('.account-toolbar')).toBeNull();
    fireEvent.change(selector, { target: { value: 'player' } });
    await waitFor(() => expect((screen.getByRole('combobox', { name: 'Player workspace' }) as HTMLSelectElement).value).toBe('player'));
    fireEvent.click(screen.getByLabelText('Account menu'));
    fireEvent.click(screen.getByRole('button', { name: 'Manage team' }));
    expect(screen.getByRole('dialog', { name: 'Add an academy account' })).toBeTruthy();
  });

  it('keeps sign-in and sign-out working with the integrated account menu', async () => {
    const identity = {
      user: { id: 'player', academy_id: 'academy', name: 'Test player', email: 'player@example.test', role: 'player' },
      csrf: 'test-csrf',
      workspaces: [{ id: 'player', name: 'Test player', role: 'player' }],
    };
    const defaults = api.getMockImplementation()!;
    api.mockImplementation(async (path, options) => {
      if (path === '/auth/config') return { enabled: true, setup_available: false } as never;
      if (path === '/auth/me') throw new Error('Sign-in required.');
      if (path === '/auth/login') return identity as never;
      if (path === '/auth/logout') return { ok: true } as never;
      return defaults(path, options);
    });
    render(<AccountGate><App/></AccountGate>);
    expect(await screen.findByRole('heading', { name: 'Sign in to Courtside' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'player@example.test' } });
    fireEvent.change(screen.getByLabelText('Passphrase'), { target: { value: 'test-only-passphrase' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('combobox', { name: 'Player workspace' })).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Account menu'));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { name: 'Sign in to Courtside' })).toBeTruthy();
    expect(api).toHaveBeenCalledWith('/auth/logout', { method: 'POST' });
  });
});
