import { API, workspacePrefix } from './api';
import type { Metric, Shot, Tip } from './types';

export interface LivePoint { x:number; y:number; confidence:number }
export interface LivePose { player_id:string; side:'near'|'far'; keypoints:LivePoint[] }
export interface LiveBall { x:number; y:number; time:number; confidence:number }
export interface LiveShot extends Shot { rating:number|null; experimental:boolean; metrics:Metric[]; tips:Tip[] }
export interface LiveFrame { type:'frame'; timestamp:number; width:number; height:number; poses:LivePose[]; ball:LiveBall|null; ball_trail:LiveBall[]; players_detected:number; shots_total:number; shot_counts:Record<string,number>; latest_shot:LiveShot|null; session_rating:number|null; processing_ms:number; reduce_workload:boolean; coach_validated:boolean; classifier:string; status:string }
export const liveSocketUrl=()=>{const url=new URL(`${workspacePrefix()}/api/live`,API||window.location.origin);url.protocol=url.protocol==='https:'?'wss:':'ws:';return url.toString();};
export const ratingLabel=(rating:number|null)=>rating===null?'Waiting for a measurable shot':rating>=80?'Mostly within targets':rating>=50?'Mixed target match':'Review with your coach';
export function cameraError(error:unknown){const value=error as {name?:string;message?:string}|null;return value?.name==='NotAllowedError'?'Camera permission was denied. Allow camera access in your browser.':value?.name==='NotFoundError'?'No camera found. Connect a webcam or use your phone.':value?.message||'Could not start the camera.';}
export const CONNECTIONS=[[0,1],[0,2],[1,3],[2,4],[5,6],[5,7],[7,9],[6,8],[8,10],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];

export function drawLiveOverlay(canvas:HTMLCanvasElement,frame:LiveFrame){
  canvas.width=frame.width;canvas.height=frame.height;
  const context=canvas.getContext('2d');if(!context)return;
  context.clearRect(0,0,canvas.width,canvas.height);
  for(const pose of frame.poses){
    const color=pose.side==='near'?'#d8f39b':'#86dce7';context.strokeStyle=color;context.fillStyle=color;context.lineWidth=3;
    for(const [a,b] of CONNECTIONS){const p=pose.keypoints[a],q=pose.keypoints[b];if(Math.min(p.confidence,q.confidence)<.65)continue;context.beginPath();context.moveTo(p.x,p.y);context.lineTo(q.x,q.y);context.stroke();}
    for(const point of pose.keypoints){if(point.confidence<.65)continue;context.beginPath();context.arc(point.x,point.y,4,0,Math.PI*2);context.fill();}
    const hip=pose.keypoints[11];context.font='bold 16px sans-serif';context.fillText(pose.side==='near'?'NEAR PLAYER':'FAR PLAYER',Math.max(8,hip.x-40),Math.max(20,hip.y-25));
  }
  context.strokeStyle='#f2dc72';context.lineWidth=3;context.beginPath();
  frame.ball_trail.forEach((point,index)=>index?context.lineTo(point.x,point.y):context.moveTo(point.x,point.y));context.stroke();
  if(frame.ball){context.fillStyle='#f2dc72';context.beginPath();context.arc(frame.ball.x,frame.ball.y,7,0,Math.PI*2);context.fill();}
}
