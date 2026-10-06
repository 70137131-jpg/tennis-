import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ShieldCheck, LogOut, Users, LoaderCircle, ChevronDown } from 'lucide-react';
import { configureAccount, request, type AccountUser, type Workspace } from './api';
import { BallMark, Modal } from './components';
import './production.css';

interface Identity {user:AccountUser;csrf:string;workspaces:Workspace[]}
interface AccountControlsValue {
  identity: Identity;
  workspace: string;
  switchWorkspace: (value: string) => void;
  manageTeam: () => void;
  logout: () => Promise<void>;
}
const AccountControlsContext = createContext<AccountControlsValue | null>(null);
export function useWorkspaceAccount() { return useContext(AccountControlsContext); }

export function AccountControls() {
  const account = useContext(AccountControlsContext);
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (event: PointerEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape' : !menu.current?.contains(event.target as Node)) {
        if (menu.current) menu.current.open = false;
      }
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', close);
    };
  }, []);
  if (!account) return null;
  const { identity, workspace, switchWorkspace, manageTeam, logout } = account;
  return <div className="account-controls">
    <label className="account-workspace"><Users size={16}/><span className="workspace-select-label" aria-hidden="true">Workspace</span>
      <select aria-label="Player workspace" value={workspace} onChange={event => switchWorkspace(event.target.value)}>
        {identity.workspaces.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}
      </select>
    </label>
    <details className="account-menu" ref={menu}>
      <summary aria-label="Account menu"><span className="avatar">{identity.user.name.slice(0, 1).toUpperCase()}</span><ChevronDown size={13}/></summary>
      <div className="account-menu-content"><strong>{identity.user.name}</strong><small>{identity.user.role}</small>
        {identity.user.role === 'admin' && <button onClick={() => { if (menu.current) menu.current.open = false; manageTeam(); }}><Users size={16}/>Manage team</button>}
        <button onClick={() => { if (menu.current) menu.current.open = false; void logout(); }}><LogOut size={16}/>Sign out</button>
      </div>
    </details>
  </div>;
}
export default function AccountGate({children}:{children:ReactNode}) {
  const [enabled,setEnabled]=useState<boolean|null>(null);
  const [setup,setSetup]=useState(false);
  const [identity,setIdentity]=useState<Identity|null>(null);
  const [workspace,setWorkspace]=useState('');
  const [email,setEmail]=useState('');const [password,setPassword]=useState('');
  const [name,setName]=useState('');const [academy,setAcademy]=useState('');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const [team,setTeam]=useState(false);const [role,setRole]=useState('player');
  const [message,setMessage]=useState('');
  const accept=(value:Identity)=>{const selected=value.workspaces.find(w=>w.id===value.user.id)?.id||value.workspaces[0]?.id||'';configureAccount({user:value.user,csrf:value.csrf,workspace:selected});setIdentity(value);setWorkspace(selected);sessionStorage.removeItem('courtside-token');};
  useEffect(()=>{let mounted=true;void request<{enabled:boolean;setup_available:boolean}>('/auth/config').then(async config=>{if(!mounted)return;setEnabled(config.enabled);setSetup(config.setup_available);if(config.enabled){try{const value=await request<Identity>('/auth/me');if(mounted)accept(value);}catch{configureAccount(null);}}}).catch(()=>{if(mounted)setEnabled(false);});return()=>{mounted=false;};},[]);
  const submit=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setError('');try{if(setup){await request('/auth/setup',{method:'POST',body:JSON.stringify({email,password,name,academy})});setSetup(false);}accept(await request<Identity>('/auth/login',{method:'POST',body:JSON.stringify({email,password})}));setPassword('');}catch(err){setError((err as Error).message);}finally{setBusy(false);}};
  const logout=async()=>{try{await request('/auth/logout',{method:'POST'});}finally{configureAccount(null);setIdentity(null);setWorkspace('');localStorage.removeItem('courtside-settings');localStorage.removeItem('courtside-mode');}};
  const switchWorkspace=(value:string)=>{if(!identity)return;configureAccount({user:identity.user,csrf:identity.csrf,workspace:value});setWorkspace(value);};
  const addMember=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setError('');try{await request('/admin/users',{method:'POST',body:JSON.stringify({email,password,name,role})});const value=await request<Identity>('/auth/me');setIdentity(value);setMessage('Account created. Share its initial passphrase privately.');setPassword('');setEmail('');setName('');}catch(err){setError((err as Error).message);}finally{setBusy(false);}};
  if(enabled===null)return <div className="account-loading" role="status"><LoaderCircle className="spin"/>Opening your workspace…</div>;
  if(!enabled)return <>{children}</>;
  if(!identity)return <main className="account-entry"><div className="account-story"><BallMark/><span className="eyebrow">COURTSIDE ACADEMY</span><h1>Your court.<br/>Your team.<br/>A clearer game.</h1><p>A private place for live coaching and measurable progress.</p><div><ShieldCheck size={18}/>Individual accounts. Private player workspaces.</div></div><form className="account-form" onSubmit={submit}><span className="eyebrow">{setup?'FIRST COURT, FIRST ACCOUNT':'WELCOME BACK'}</span><h2>{setup?'Set up your academy':'Sign in to Courtside'}</h2><p>{setup?'Create the academy administrator on this machine.':'Use the account provided by your academy administrator.'}</p>{setup&&<><label>Academy name<input required value={academy} onChange={e=>setAcademy(e.target.value)} maxLength={100}/></label><label>Your name<input required autoComplete="name" value={name} onChange={e=>setName(e.target.value)} maxLength={80}/></label></>}<label>Email<input required type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} maxLength={120}/></label><label>Passphrase<input required type="password" autoComplete={setup?'new-password':'current-password'} minLength={15} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><small>Use 15 or more characters. Your passphrase is never stored as plain text.</small>{error&&<p className="form-error" role="alert">{error}</p>}<button className="primary-button" disabled={busy}>{busy?<LoaderCircle className="spin" size={16}/>:<ShieldCheck size={16}/>} {busy?'Connecting…':setup?'Create academy & sign in':'Sign in'}</button></form></main>;
  return <AccountControlsContext.Provider value={{ identity, workspace, switchWorkspace, logout, manageTeam: () => {setTeam(true);setName('');setEmail('');setPassword('');setError('');setMessage('');} }}><div className="account-active"><div key={workspace}>{children}</div>{team&&<Modal title="Add an academy account" subtitle="Players see their own workspace. Coaches can review players in this academy." onClose={()=>setTeam(false)}><form className="account-member" onSubmit={addMember}><label>Name<input required value={name} onChange={e=>setName(e.target.value)} maxLength={80}/></label><label>Email<input required type="email" value={email} onChange={e=>setEmail(e.target.value)} maxLength={120}/></label><label>Role<select value={role} onChange={e=>setRole(e.target.value)}><option value="player">Player</option><option value="coach">Coach</option><option value="admin">Administrator</option></select></label><label>Initial passphrase<input required type="password" minLength={15} maxLength={128} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>{error&&<p role="alert" className="form-error">{error}</p>}{message&&<p role="status">{message}</p>}<button className="primary-button" disabled={busy}>Create account</button></form></Modal>}</div></AccountControlsContext.Provider>;
}
