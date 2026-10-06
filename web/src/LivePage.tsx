import { useEffect, useRef, useState } from 'react';
import { Camera, CircleStop, Radio, ShieldCheck, Activity, Target, Crosshair, AlertCircle, LoaderCircle, Volume2, VolumeX, SwitchCamera } from 'lucide-react';
import type { Settings } from './types';
import { capitalize, Modal, PageTitle } from './components';
import { token } from './api';
import { cameraError, drawLiveOverlay, liveSocketUrl, type LiveFrame } from './live';
import LiveShotAssessment from './LiveShotAssessment';

export default function LivePage({settings,online,modelReady}:{settings:Settings;online:boolean;modelReady:boolean}){
  const [state,setState]=useState<'idle'|'starting'|'live'>('idle');const [error,setError]=useState('');const [frame,setFrame]=useState<LiveFrame|null>(null);const [rtt,setRtt]=useState(0);const [consent,setConsent]=useState(false);const [experimental,setExperimental]=useState(true);const [junior,setJunior]=useState(false);const [guardian,setGuardian]=useState('');const [guardianConsent,setGuardianConsent]=useState(false);const [assent,setAssent]=useState(false);const [facing,setFacing]=useState<'environment'|'user'>('environment');const [devices,setDevices]=useState<MediaDeviceInfo[]>([]);const [device,setDevice]=useState('');const [sound,setSound]=useState(false);const [calibrating,setCalibrating]=useState(false);const [calibrationImage,setCalibrationImage]=useState('');const [corners,setCorners]=useState<number[][]>([]);
  const video=useRef<HTMLVideoElement>(null);const overlay=useRef<HTMLCanvasElement>(null);const capture=useRef<HTMLCanvasElement|null>(null);const stream=useRef<MediaStream|null>(null);const socket=useRef<WebSocket|null>(null);const timer=useRef<ReturnType<typeof setTimeout>|null>(null);const generation=useRef(0);const watchdog=useRef<ReturnType<typeof setTimeout>|null>(null);const sentAt=useRef(0);const maxWidth=useRef(960);const soundRef=useRef(sound);const spoken=useRef('');const recent=useRef<Array<{id:string;type:string;rating:number|null}>>([]);
  soundRef.current=sound;
  const stop=()=>{generation.current++;if(watchdog.current)clearTimeout(watchdog.current);if(timer.current)clearTimeout(timer.current);timer.current=null;const ws=socket.current;socket.current=null;if(ws){if(ws.readyState===WebSocket.OPEN)ws.send('stop');ws.close();}stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;if(video.current)video.current.srcObject=null;capture.current=null;if(overlay.current)overlay.current.width=overlay.current.width;setState('idle');if('speechSynthesis' in window)window.speechSynthesis.cancel();};
  useEffect(()=>()=>{generation.current++;if(watchdog.current)clearTimeout(watchdog.current);if(timer.current)clearTimeout(timer.current);socket.current?.close();stream.current?.getTracks().forEach(track=>track.stop());if('speechSynthesis' in window)window.speechSynthesis.cancel();},[]);
  const start=async()=>{
    setError('');setFrame(null);setRtt(0);recent.current=[];spoken.current='';maxWidth.current=960;
    if(!online||!modelReady){setError('Start the local Courtside server and install its pose model first.');return;}
    if(!navigator.mediaDevices?.getUserMedia){setError('Camera access requires localhost or a secure HTTPS connection. Open this page securely on your phone.');return;}
    if(!consent||(junior&&(!guardian.trim()||!guardianConsent||!assent))){setError('Complete the camera processing and junior consent fields first.');return;}
    setState('starting');const run=++generation.current;
    try{
      const camera=await navigator.mediaDevices.getUserMedia({audio:false,video:device?{deviceId:{exact:device},width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30}}:{facingMode:{ideal:facing},width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30}}});
      if(generation.current!==run){camera.getTracks().forEach(track=>track.stop());return;}
      stream.current=camera;const element=video.current;if(!element)throw new Error('Camera preview unavailable');element.srcObject=camera;await element.play();
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput'));
      const ws=new WebSocket(liveSocketUrl());socket.current=ws;capture.current=document.createElement('canvas');
      const next=()=>{
        if(generation.current!==run||ws.readyState!==WebSocket.OPEN||!video.current||!capture.current)return;
        const source=video.current,canvas=capture.current;if(source.readyState<2){timer.current=setTimeout(next,100);return;}
        const scale=Math.min(1,maxWidth.current/source.videoWidth);canvas.width=Math.round(source.videoWidth*scale);canvas.height=Math.round(source.videoHeight*scale);canvas.getContext('2d')?.drawImage(source,0,0,canvas.width,canvas.height);
        canvas.toBlob(async blob=>{if(!blob||generation.current!==run||ws.readyState!==WebSocket.OPEN)return;sentAt.current=performance.now();if(watchdog.current)clearTimeout(watchdog.current);watchdog.current=setTimeout(()=>{if(generation.current===run){setError('Live analysis stopped responding. Restart the feed.');stop();}},10000);const bytes=await blob.arrayBuffer();if(generation.current===run&&ws.readyState===WebSocket.OPEN)ws.send(bytes);},'image/jpeg',.72);
      };
      const startTimeout=setTimeout(()=>{if(generation.current===run&&ws.readyState!==WebSocket.CLOSED){setError('Live analysis did not respond. Check the server connection and pose model.');stop();}},15000);
      ws.onopen=()=>ws.send(JSON.stringify({type:'start',token:token(),options:{handedness:settings.handedness,level:settings.level,age_group:junior?'junior':'adult',processing_consent:consent,guardian_consent:guardianConsent,guardian_name:guardian,player_assent:assent,experimental_feedback:experimental,court_corners:corners.length===4?corners:null}}));
      ws.onmessage=event=>{
        if(generation.current!==run)return;clearTimeout(startTimeout);const message=JSON.parse(event.data);
        if(message.type==='error'){setError(message.message);stop();return;}
        if(message.type==='ready'){setState('live');next();return;}
        if(message.type!=='frame')return;if(watchdog.current)clearTimeout(watchdog.current);
        const value=message as LiveFrame;setFrame(value);setRtt(Math.round(performance.now()-sentAt.current));if(overlay.current)drawLiveOverlay(overlay.current,value);
        if(value.reduce_workload)maxWidth.current=Math.max(640,maxWidth.current-160);
        const shot=value.latest_shot;if(shot&&recent.current.at(-1)?.id!==shot.id){recent.current=[...recent.current,{id:shot.id,type:shot.type,rating:shot.rating}].slice(-8);if(soundRef.current&&shot.tips[0]&&spoken.current!==shot.id&&'speechSynthesis' in window){spoken.current=shot.id;window.speechSynthesis.speak(new SpeechSynthesisUtterance(shot.tips[0].title));}}
        const wait=Math.max(20,100-value.processing_ms);timer.current=setTimeout(next,wait);
      };
      ws.onerror=()=>{clearTimeout(startTimeout);if(generation.current===run){setError('Could not connect to live analysis. Check your server and workspace access token.');stop();}};
      ws.onclose=()=>{clearTimeout(startTimeout);if(generation.current===run){setError('Live connection ended. Restart the camera to reconnect.');stop();}};
    }catch(err){if(generation.current!==run)return;setError(cameraError(err));stop();}
  };

  const active=state!=='idle';const shot=frame?.latest_shot;
  const blockedReason = !online ? 'Connect your local server to start analysis.'
    : !modelReady ? 'Set up the pose model before starting.'
    : !consent ? 'Confirm processing permission to enable the camera.'
    : junior && (!guardian.trim() || !guardianConsent || !assent) ? 'Complete guardian consent and player agreement.'
    : null;
  return <>
    <PageTitle eyebrow="YOUR COURT, IN FOCUS" title="Live court" description="Track your movement. Review each shot. Find your next adjustment.">
      <span className="session-privacy"><ShieldCheck size={15}/>Private session · no recording</span>
    </PageTitle>
    <div className="live-layout">
      <section className="live-camera-panel" aria-label="Camera and live measurements">
        <div className="live-camera-stage">
          <video ref={video} autoPlay playsInline muted aria-label="Live camera preview"/>
          <canvas ref={overlay} aria-label="Live player skeleton and ball tracking overlay"/>
          {!active&&<div className="live-camera-empty">
            <svg className="live-court-art" viewBox="0 0 700 430" aria-hidden="true"><g fill="none" stroke="currentColor" strokeWidth="1.3">
              <path d="M206 118H494L640 372H60ZM227 118L143 372M473 118L557 372M161 196H539M103 298H597M193 196L170 298M507 196L530 298M350 196V298"/>
              <path d="M153 212H547" strokeDasharray="3 4"/><circle cx="468" cy="184" r="5"/><circle cx="267" cy="308" r="8"/>
            </g></svg>
            <span className="camera-empty-icon"><Camera size={30}/></span>
            <span className="camera-empty-eyebrow">LIVE PERFORMANCE ANALYSIS</span>
            <h2>A clearer view<br/>of your game.</h2>
            <p>Choose your camera and confirm permission<br className="desktop-break"/> to begin your session.</p>
            <span className="camera-empty-footnote"><ShieldCheck size={13}/>Your camera stays off until you start.</span>
          </div>}
          {state==='starting'&&<div className="live-starting"><LoaderCircle size={28} className="spin"/><span>Connecting camera & analysis…</span></div>}
          <div className={'live-feed-badge '+(state==='live'?'on':'')}><span/>{state==='live'?'LIVE TRACKING':state==='starting'?'CONNECTING':'CAMERA OFF'}</div>
          <div className="camera-stage-label"><Crosshair size={13}/>COURTSIDE / LIVE</div>
          {active&&<div className="live-camera-bottom"><span>{frame?.status||'Finding players…'}</span><span>{rtt?rtt+' ms round trip':''}</span></div>}
        </div>
        <div className="live-feed-controls">
          <div><span className={state==='live'?'good-dot':'offline-dot'}/>{state==='live'?'Analyzing on your machine':state==='starting'?'Connecting your camera':'Camera is off'}</div>
          <button className="secondary-button" onClick={()=>setSound(!sound)} aria-label={sound?'Mute spoken tips':'Enable spoken tips'} aria-pressed={sound}>{sound?<Volume2 size={15}/>:<VolumeX size={15}/>}Audio tips {sound?'on':'off'}</button>
        </div>
        {error&&<div role="alert" className="form-error"><AlertCircle size={17}/>{error}</div>}
        <div className="live-telemetry" aria-label="Live session measurements">
          <div><Activity size={17}/><span>Players tracked</span><strong>{frame?.players_detected??'—'}<small> / 2</small></strong></div>
          <div><Crosshair size={17}/><span>Ball candidate</span><strong>{frame?.ball?'Detected':state==='live'?'Searching':'—'}</strong></div>
          <div><Radio size={17}/><span>Shot candidates</span><strong>{frame?.shots_total??'—'}</strong></div>
          <div><Target size={17}/><span>Target match</span><strong>{frame?.session_rating??'—'}<small>{frame?.session_rating!==null&&frame?.session_rating!==undefined?'%':''}</small></strong></div>
        </div>
        <section className="panel live-recent"><div className="panel-heading"><div><span className="eyebrow">SESSION ACTIVITY</span><h2>Recent shots</h2></div><span className="small-badge">{shot?'Measured 2D proxies':'Waiting for a shot'}</span></div>
          {recent.current.length?<div className="live-shot-strip">{recent.current.map((item,index)=><div key={item.id}><span>SHOT {index+1}</span><strong>{capitalize(item.type)}</strong><small>{item.rating===null?'Not measurable':item.rating+'% target match'}</small></div>)}</div>
            :<div className="live-activity-empty"><Radio size={23}/><div><strong>Your session starts here</strong><p>Shots appear after follow-through. Keep your full body visible for reliable measurements.</p></div></div>}
        </section>
      </section>
      <aside className="live-coach-column" aria-label="Session setup and coaching">
        <section className="panel live-setup">
          <div className="setup-heading"><span className="section-number">01</span><div><span className="eyebrow">BEFORE YOU PLAY</span><h2>Set up your session</h2></div><Camera size={19}/></div>
          <fieldset disabled={active}>
            <label>Camera{devices.length?<select value={device} onChange={event=>setDevice(event.target.value)}><option value="">Default camera</option>{devices.map(d=><option key={d.deviceId} value={d.deviceId}>{d.label||'Camera'}</option>)}</select>:<select value={facing} onChange={event=>setFacing(event.target.value as typeof facing)}><option value="environment">Rear / court camera</option><option value="user">Front / webcam</option></select>}</label>
            <p className="camera-placement-note">Use a fixed view behind the baseline, with both players fully in frame.</p>
            <label className="checkbox-label processing-permission"><input type="checkbox" checked={consent} onChange={event=>setConsent(event.target.checked)}/><span>I have permission to process everyone in the camera view.<small>Frames are not saved or used for training.</small></span></label>
            <label className="checkbox-label junior-toggle"><input type="checkbox" checked={junior} onChange={event=>setJunior(event.target.checked)}/><span>A junior player is in the camera view.</span></label>
            {junior&&<div className="junior-consent"><label>Consenting guardian’s name<input value={guardian} onChange={event=>setGuardian(event.target.value)} maxLength={100}/></label><label className="checkbox-label"><input type="checkbox" checked={guardianConsent} onChange={event=>setGuardianConsent(event.target.checked)}/><span>Guardian gave explicit processing consent.</span></label><label className="checkbox-label"><input type="checkbox" checked={assent} onChange={event=>setAssent(event.target.checked)}/><span>Junior agrees to live analysis.</span></label></div>}
            <details className="live-options"><summary>Coaching preferences<SwitchCamera size={15}/></summary>
              <label className="checkbox-label"><input type="checkbox" checked={experimental} onChange={event=>setExperimental(event.target.checked)}/><span>Preview experimental coaching<small>Provisional ratings from measured movement.</small></span></label>
            </details>
          </fieldset>
          <button className={active?'danger-button live-start-button':'primary-button live-start-button'} onClick={active?stop:start} disabled={!active&&blockedReason!==null} aria-describedby="live-start-reason">
            {state==='starting'?<LoaderCircle size={17} className="spin"/>:active?<CircleStop size={17}/>:<Camera size={17}/>} {active?'Stop live feed':'Start live feed'}
          </button>
          <p id="live-start-reason" className="live-start-reason">{active?'Stop closes the camera and ends live analysis.':blockedReason||'Ready. Your browser will ask for camera access.'}</p>
          <div className="live-setup-footer"><ShieldCheck size={14}/><span>Local processing. No video recording.</span></div>
          <button className="text-link calibration-action" disabled={!frame||!active} onClick={()=>{if(!capture.current)return;setCalibrationImage(capture.current.toDataURL('image/jpeg'));stop();setCorners([]);setCalibrating(true);}}><Crosshair size={14}/>{corners.length===4?'Recalibrate court':'Calibrate court'}<span>{!active?'Available during a live feed':'Select court corners'}</span></button>
        </section>
        <LiveShotAssessment shot={shot??null} coachValidated={frame?.coach_validated??false}/>
      </aside>
    </div>
  {calibrating&&<Modal title="Calibrate the live court" subtitle="Select far left, far right, near right, then near left singles corners." onClose={()=>setCalibrating(false)} wide><div className="calibration-image" onClick={event=>{if(corners.length>=4)return;const rect=event.currentTarget.getBoundingClientRect();setCorners([...corners,[(event.clientX-rect.left)/rect.width,(event.clientY-rect.top)/rect.height]]);}}><img src={calibrationImage} alt="Frozen camera frame for court corner calibration"/>{corners.map((point,index)=><span className="calibration-point" key={index} style={{left:`${point[0]*100}%`,top:`${point[1]*100}%`}}>{index+1}</span>)}</div><div className="modal-actions"><button className="secondary-button" onClick={()=>setCorners([])}>Reset points</button><span>{corners.length}/4 corners</span><button className="primary-button" disabled={corners.length!==4} onClick={()=>setCalibrating(false)}>Save calibration</button></div><p className="field-help">Start the live feed again to use these court corners.</p></Modal>}</>;
}


