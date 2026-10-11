import { useCallback, useEffect, useRef, useState } from 'react';
import { LayoutDashboard, Video, ChartNoAxesCombined, MessageSquareText, Settings as SettingsIcon, CircleHelp, Plus, ChevronDown, ArrowUpRight, Bell, Menu, X, Search, ArrowRight, Upload, ShieldCheck, Camera, Check, WifiOff } from 'lucide-react';
import type { Review, Session, Settings } from './types';
import { ApiError, preserveMedia, request } from './api';
import ProductionPage from './ProductionPage';
import { AccountControls, useWorkspaceAccount } from './AccountGate';
import { demoSessions, defaultSettings } from './demo';
import { BallMark, Modal } from './components';
import { SwingHome, SwingLibrary } from './SwingViews';
import LivePage from './LivePage';
import './live.css';
import { Notes, Progress, SettingsPage } from './Pages';
import UploadDialog from './UploadDialog';
import SessionReport from './SessionReport';

const navItems=[{id:'overview',label:'Home',icon:LayoutDashboard},{id:'sessions',label:'Sessions',icon:Video},{id:'live',label:'Live camera',icon:Camera},{id:'progress',label:'Stats',icon:ChartNoAxesCombined},{id:'notes',label:'Coaching',icon:MessageSquareText}];
const readRoute=()=>window.location.hash.slice(1)||'sessions';
function savedSettings(accounted:boolean): Settings {if(accounted)return defaultSettings;try{return {...defaultSettings,...JSON.parse(localStorage.getItem('courtside-settings')||'{}')};}catch{return defaultSettings;}}

export default function App() {
  const academy = useWorkspaceAccount();
  const [route,setRoute]=useState(readRoute);const [sessions,setSessions]=useState<Session[]>(academy?[]:demoSessions);const [settings,setSettings]=useState<Settings>(()=>academy?{...defaultSettings,display_name:academy.identity.user.name,player_name:academy.identity.user.name}:savedSettings(false));const [reviews,setReviews]=useState<Review[]>([]);const [connection,setConnection]=useState<'connecting'|'online'|'offline'|'locked'>('connecting');const [modelReady,setModelReady]=useState(false);const [mode,setMode]=useState(academy?'real':localStorage.getItem('courtside-mode')||'demo');const [upload,setUpload]=useState(false);const [help,setHelp]=useState(false);const [mobile,setMobile]=useState(false);const [bell,setBell]=useState(false);const [toast,setToast]=useState('');
  const online=connection==='online';
  const [compact, setCompact] = useState(() => window.innerWidth <= 900);
  useEffect(() => {
    const update = () => setCompact(window.innerWidth <= 900);
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  const sidebar = useRef<HTMLElement>(null);
  const mobileTrigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!mobile) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const controls = () => Array.from(sidebar.current?.querySelectorAll<HTMLButtonElement>('button') || []);
    controls()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobile(false);
      if (event.key === 'Tab') {
        const items = controls();
        const first = items[0], last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    const onResize = () => { if (window.innerWidth > 900) setMobile(false); };
    window.addEventListener('resize', onResize);
    document.addEventListener('keydown', keydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', keydown);
      window.removeEventListener('resize', onResize);
      mobileTrigger.current?.focus();
    };
  }, [mobile]);

  const navigate=(page:string)=>{window.location.hash=page;setRoute(page);setMobile(false);setBell(false);window.scrollTo({top:0,behavior:'instant'});};
  const notify=useCallback((message:string)=>setToast(message),[]);
  const refresh=useCallback(async()=>{try{const health=await request<{model_ready:boolean}>('/health');setModelReady(health.model_ready);const [rows,prefs,ratings]=await Promise.all([request<Session[]>('/sessions'),request<Settings>('/settings'),request<Review[]>('/reviews')]);setSessions(previous=>preserveMedia(previous,rows));setSettings(previous=>JSON.stringify(previous)===JSON.stringify(prefs)?previous:prefs);setReviews(ratings);setConnection('online');}catch(err){if(err instanceof ApiError&&err.status===401){setSessions([]);setReviews([]);setSettings(defaultSettings);setConnection('locked');}else setConnection('offline');}},[]);
  useEffect(()=>{void refresh();const interval=setInterval(()=>void refresh(),5000);return()=>clearInterval(interval);},[refresh]);
  useEffect(()=>{const handler=()=>{setRoute(readRoute());setMobile(false);};window.addEventListener('hashchange',handler);return()=>window.removeEventListener('hashchange',handler);},[]);
  useEffect(()=>{if(!toast)return;const timeout=setTimeout(()=>setToast(''),4500);return()=>clearTimeout(timeout);},[toast]);
  const changeMode=(value:string)=>{setMode(value);localStorage.setItem('courtside-mode',value);};
  const selectedId=route.startsWith('session/')?route.slice(8):null;const selected=sessions.find(s=>s.id===selectedId);const activePage=selectedId?'sessions':route;
  const visible=sessions.filter(s=>mode==='demo'?s.is_demo:!s.is_demo);const pageLabel=selected?.title||[...navItems,{id:'settings',label:'Settings'},{id:'production',label:'Release checks'}].find(n=>n.id===activePage)?.label||'Overview';
  const deleteSession=async(id:string)=>{if(online)await request(`/sessions/${id}`,{method:'DELETE'});else if(!sessions.find(s=>s.id===id)?.is_demo)throw new Error('Reconnect the local server to delete this session.');setSessions(s=>s.filter(row=>row.id!==id));notify('Session and its artifacts deleted.');};
  const saveSettings=async(value:Settings)=>{if(online)await request('/settings',{method:'PUT',body:JSON.stringify(value)});setSettings(value);if(!academy)localStorage.setItem('courtside-settings',JSON.stringify(value));notify(online?'Workspace preferences saved.':'Preferences saved in this browser.');};

  return <div className="app-shell">
    <a href="#main-content" className="skip-link" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus();}}>Skip to content</a>
    {mobile&&<div className="mobile-backdrop" onClick={()=>setMobile(false)}/>}
    <aside ref={sidebar} id="workspace-navigation" className={'sidebar ' + (mobile?'open':'')} inert={compact&&!mobile} role={mobile?'dialog':undefined} aria-modal={mobile?true:undefined} aria-label={mobile?'Workspace navigation':undefined}>
      <div className="brand-row"><button className="brand" onClick={()=>navigate('sessions')} aria-label="Courtside home"><BallMark/><span>courtside<span className="brand-dot">.</span></span></button>
        <button className="icon-button sidebar-close" onClick={()=>setMobile(false)} aria-label="Close navigation"><X size={20}/></button>
      </div>
      <div className="workspace-label">SEE YOUR GAME. IMPROVE YOUR GAME.</div>
      <div className="sidebar-divider"/><div className="nav-caption">YOUR GAME</div>
      <nav aria-label="Main navigation">{navItems.map(({id,label,icon:Icon})=>
        <button key={id} className={'nav-item ' + (activePage===id?'active':'')} onClick={()=>navigate(id)} aria-current={activePage===id?'page':undefined}>
          <Icon size={19}/><span>{label}</span>{id==='sessions'&&<span className="nav-count">{visible.length}</span>}
        </button>)}
      </nav>
      <div className="sidebar-session-note"><span className="sidebar-court-symbol" aria-hidden="true"/><span>Built for your time on court.<small>Private, local analysis.</small></span></div>
      <div className="sidebar-bottom"><div className="nav-caption">WORKSPACE</div>
        <button className={'nav-item ' + (activePage==='settings'?'active':'')} onClick={()=>navigate('settings')} aria-current={activePage==='settings'?'page':undefined}><SettingsIcon size={18}/>Settings</button>
        <button className={'nav-item ' + (activePage==='production'?'active':'')} onClick={()=>navigate('production')} aria-current={activePage==='production'?'page':undefined}><ShieldCheck size={18}/>Release checks</button>
        <button className="nav-item" onClick={()=>{setMobile(false);setHelp(true);}}><CircleHelp size={18}/>Help & setup</button>
        <div className="sidebar-divider"/>
        <button className="profile-button" onClick={()=>navigate('settings')}><span className="avatar">{settings.display_name.slice(0,2).toUpperCase()}</span>
          <span><strong>{settings.player_name}</strong><small>{academy?'Academy workspace':'Personal workspace'}</small></span><ChevronDown size={14}/>
        </button>
      </div>
    </aside>
    <div className="main-shell" inert={mobile}><header className="topbar">
      <div className="topbar-left"><button ref={mobileTrigger} className="icon-button mobile-menu" onClick={()=>setMobile(!mobile)} aria-label="Open navigation" aria-expanded={mobile} aria-controls="workspace-navigation"><Menu size={22}/></button>
        <span className="sv-sport"><BallMark small/>Tennis</span><span className="breadcrumb-slash">/</span><span className="breadcrumb-current">{pageLabel}</span>
      </div>
      <div className="topbar-right">
        <span className={'server-indicator ' + (online?'connected':'')} title={online?'Connected to local analysis':connection==='locked'?'Workspace access required':connection==='connecting'?'Connecting to local analysis':'Local analysis is offline'}>
          <span/>{online?'Connected':connection==='connecting'?'Connecting':connection==='locked'?'Locked':'Offline'}
        </span>
        {activePage!=='live'&&!academy&&<div className="workspace-switch"><span className="workspace-select-label" aria-hidden="true">Workspace</span><select aria-label="Workspace data" value={mode} onChange={e=>changeMode(e.target.value)}><option value="demo">Demo workspace</option><option value="real">Your sessions</option></select><ChevronDown size={12}/></div>}
        <span className="topbar-divider"/>
        <button className="icon-button header-help" aria-label="Getting started" onClick={()=>setHelp(true)}><CircleHelp size={19}/></button>
        <div className="notification-wrap"><button className={'icon-button ' + (bell?'selected':'')} aria-label="Notifications" aria-expanded={bell} onClick={()=>setBell(!bell)}><Bell size={19}/>{sessions.some(s=>s.status==='processing'||s.status==='queued')&&<span className="notification-dot"/>}</button>
          {bell&&<div className="notifications"><h3>Workspace updates</h3>{sessions.filter(s=>!s.is_demo&&s.status!=='completed').length?sessions.filter(s=>!s.is_demo&&s.status!=='completed').slice(0,5).map(s=><button key={s.id} onClick={()=>navigate('session/'+s.id)}><span className={s.status==='failed'?'notice-error':'good-dot'}/><div><strong>{s.title}</strong><span>{s.stage}{s.status==='processing'?' · '+s.progress+'%':''}</span></div><ArrowRight size={14}/></button>):<p>No new updates. Your session results will appear here.</p>}<button className="text-link" onClick={()=>{setBell(false);setUpload(true);}}>Upload a session<Plus size={14}/></button></div>}
        </div>
        {academy?<AccountControls/>:<button className="topbar-avatar avatar" aria-label="Player settings" onClick={()=>navigate('settings')}>{settings.display_name.slice(0,1).toUpperCase()}</button>}
      </div>
    </header>
    <main id="main-content" className="main-content" tabIndex={-1}>{connection==='locked'&&<div className="connection-banner"><ShieldCheck size={16}/><span>Your private server requires an access token.</span><button onClick={()=>navigate('settings')}>Connect in Settings<ArrowRight size={14}/></button></div>}{connection==='offline'&&mode==='real'&&<div className="connection-banner"><WifiOff size={16}/><span>The local server is offline. Start Courtside to access your real sessions.</span><button onClick={()=>void refresh()}>Reconnect<ArrowRight size={14}/></button></div>}
      {selectedId?(selected?<SessionReport key={selected.id} session={selected} online={online} onBack={()=>navigate('sessions')} onDelete={deleteSession} notify={notify} refresh={refresh}/>:<div className="empty-state"><Video size={28}/><h2>Session not found</h2><p>It may have been deleted, or the local server is disconnected.</p><button className="primary-button" onClick={()=>navigate('sessions')}>Back to session library</button></div>):activePage==='live'?<LivePage settings={settings} online={online} modelReady={modelReady}/>:activePage==='production'?<ProductionPage/>:activePage==='sessions'?<SwingLibrary onRecord={()=>navigate('live')} sessions={visible} onUpload={()=>setUpload(true)} onOpen={id=>navigate(`session/${id}`)}/>:activePage==='progress'?<Progress sessions={visible}/>:activePage==='notes'?<Notes sessions={visible} online={online} reviews={reviews} onOpen={id=>navigate(`session/${id}`)}/>:activePage==='settings'?<SettingsPage settings={settings} online={online} modelReady={modelReady} onSave={saveSettings} onReconnect={refresh} notify={notify}/>:<SwingHome sessions={visible} settings={settings} goalStorageKey={academy?`courtside-weekly-goal-${academy.identity.user.id}`:undefined} onUpload={()=>setUpload(true)} onOpen={id=>navigate(`session/${id}`)} navigate={navigate}/>}
    </main><nav className="sv-bottom-nav" aria-label="Mobile navigation">{[{id:'overview',label:'Home',icon:LayoutDashboard},{id:'sessions',label:'Sessions',icon:Video},{id:'live',label:'Live',icon:Camera},{id:'progress',label:'Stats',icon:ChartNoAxesCombined},{id:'settings',label:'Profile',icon:SettingsIcon}].map(({id,label,icon:Icon})=><button key={id} className={activePage===id?'active':''} aria-current={activePage===id?'page':undefined} onClick={()=>navigate(id)}><Icon size={21}/><span>{label}</span></button>)}</nav></div>{toast&&<div className="toast" role="status"><Check size={16}/>{toast}<button onClick={()=>setToast('')} aria-label="Dismiss message"><X size={14}/></button></div>}
    {upload&&<UploadDialog settings={settings} online={online} onClose={()=>setUpload(false)} onComplete={session=>{setSessions(rows=>[session,...rows]);setUpload(false);changeMode('real');navigate(`session/${session.id}`);notify('Session uploaded. Analysis is queued.');}}/>}
    {help&&<Modal title="Getting started" subtitle="Set up your camera, analyze a session and review your measurements." onClose={()=>setHelp(false)} wide><div className="help-steps">{[{icon:Camera,title:'Set up your camera',text:'Place a fixed camera behind the baseline, centered and elevated 3–5 m. Aim for 1080p, 60 fps and a fast shutter. Keep both players in frame.'},{icon:Upload,title:'Bring your session to Courtside',text:'Upload an MP4 or MOV, choose your player and playing hand, and confirm recording permissions. Juniors need guardian consent and player assent.'},{icon:Search,title:'See the detail in every shot',text:'Review shot clips with skeleton overlays, measurable technique and confidence levels. Coach-reviewed thresholds turn measurements into explainable tips.'},{icon:ChartNoAxesCombined,title:'Build your bigger picture',text:'Use the same camera placement across sessions to compare technique trends. Share the JSON report with your coach and keep showing up.'}].map(({icon:Icon,title,text},i)=><div className="help-step" key={title}><span><Icon size={21}/></span><div><small>0{i+1}</small><h3>{title}</h3><p>{text}</p></div></div>)}</div><div className="help-setup"><h3>Start the local app</h3><p>Open a terminal in this project and run:</p><code>.venv\Scripts\courtside.exe serve</code><p>For development, run the API and <code>npm run dev</code> in separate terminals. The README includes installation, phone access and model setup instructions.</p></div><div className="privacy-note"><ShieldCheck size={18}/><p>Your video stays on your own machine. Demo sessions are synthetic. Real coaching thresholds await qualified-coach approval.</p></div><div className="modal-actions"><button className="primary-button" onClick={()=>{setHelp(false);navigate('live');}}>Open live court<ArrowUpRight size={16}/></button></div></Modal>}
  </div>;
}



