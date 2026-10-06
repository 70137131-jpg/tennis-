export const API = import.meta.env.VITE_API_URL || '';
export const token = () => sessionStorage.getItem('courtside-token') || '';
export interface AccountUser { id:string; academy_id:string; name:string; email:string; role:'admin'|'coach'|'player' }
export interface Workspace { id:string; name:string; role:string }
export let accountContext: {user:AccountUser;csrf:string;workspace:string}|null = null;
export function configureAccount(value:typeof accountContext){accountContext=value;}
export const workspacePrefix=()=>accountContext?`/api/workspaces/${accountContext.workspace}`:'';
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const rootRoute=/^\/(auth|admin|health|ready)(\/|$)/.test(path);
  const response = await fetch(`${API}${rootRoute?'':workspacePrefix()}/api${path}`, { credentials:'include', ...options, headers: { ...(!accountContext&&token() ? { Authorization: `Bearer ${token()}` } : {}), ...(accountContext&&options.method&&!['GET','HEAD'].includes(options.method)?{'X-CSRF-Token':accountContext.csrf}:{}), ...(options.body && typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  if (!response.ok) { const error = await response.json().catch(() => ({ detail: 'The server could not complete this request.' })); throw new ApiError(typeof error.detail === 'string' ? error.detail : 'Check your fields and try again.', response.status); }
  return response.json();
}
export function downloadJson(data: unknown, filename: string) { const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url); }
export function asset(url?: string) { return url ? `${API}${url}` : undefined; }

export function preserveMedia<T extends {id:string;media?:Record<string,string>}>(previous:T[],next:T[]):T[]{
  const old=new Map(previous.map(session=>[session.id,session]));
  return next.map(session=>{const prior=old.get(session.id);if(!prior?.media)return session;const media={...session.media};for(const [asset,url] of Object.entries(prior.media)){const expires=Number(new URL(url,window.location.origin).searchParams.get('expires'));if(asset in media&&expires*1000>Date.now()+60000)media[asset]=url;}return {...session,media};});
}
