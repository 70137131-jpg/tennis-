import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, preserveMedia, request } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('API access and errors', () => {
  it('keeps a valid media URL stable during polling so playback does not restart',()=>{
    const expires=Math.round(Date.now()/1000)+3600;
    const old=[{id:'s',media:{'clip.mp4':`/api/media/s/clip.mp4?expires=${expires}&signature=old`}}];
    const next=[{id:'s',media:{'clip.mp4':`/api/media/s/clip.mp4?expires=${expires+5}&signature=new`}}];
    expect(preserveMedia(old,next)[0].media['clip.mp4']).toContain('signature=old');
    expect(preserveMedia([{id:'s',media:{'clip.mp4':'/api/media/s/clip.mp4?expires=1'}}],next)[0].media['clip.mp4']).toContain('signature=new');
  });
  it('sends the workspace token and JSON content type', async () => {
    sessionStorage.setItem('courtside-token', 'test-only-token');
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ saved: true }) });
    vi.stubGlobal('fetch', fetch);
    expect(await request('/settings', { method: 'PUT', body: '{}' })).toEqual({ saved: true });
    expect(fetch).toHaveBeenCalledWith('/api/settings', expect.objectContaining({ headers: { Authorization: 'Bearer test-only-token', 'Content-Type': 'application/json' } }));
  });
  it('preserves binary uploads and content headers', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ offset: 3 }) });
    vi.stubGlobal('fetch', fetch);
    const bytes = new Uint8Array([1,2,3]).buffer;
    await request('/uploads/test?offset=0', { method: 'PUT', body: bytes, headers: { 'Content-Type': 'application/octet-stream' } });
    expect(fetch).toHaveBeenCalledWith('/api/uploads/test?offset=0', expect.objectContaining({ body: bytes, headers: { 'Content-Type': 'application/octet-stream' } }));
  });
  it('reports token expiry as a typed error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: 'Token required' }) }));
    await expect(request('/sessions')).rejects.toMatchObject({ message: 'Token required', status: 401 });
    await expect(request('/sessions')).rejects.toBeInstanceOf(ApiError);
  });
  it('handles a proxy returning an HTML error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new Error('HTML'); } }));
    await expect(request('/sessions')).rejects.toMatchObject({ status: 502, message: 'The server could not complete this request.' });
  });
});
