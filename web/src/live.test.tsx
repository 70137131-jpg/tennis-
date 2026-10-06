import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LivePage from './LivePage';
import { defaultSettings } from './demo';
import { liveSocketUrl, ratingLabel } from './live';
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
describe('live camera flow',()=>{
  it('starts frame transport and releases the camera on stop',async()=>{
    const stopTrack=vi.fn();const camera={getTracks:()=>[{stop:stopTrack}]};
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue(camera),enumerateDevices:vi.fn().mockResolvedValue([])}});
    vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
    vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({drawImage:vi.fn(),clearRect:vi.fn()} as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype,'toBlob').mockImplementation(callback=>callback({arrayBuffer:async()=>new ArrayBuffer(3)} as Blob));
    let instance:FakeSocket;
    class FakeSocket{static OPEN=1;static CLOSED=3;readyState=1;onopen:(()=>void)|null=null;onmessage:((event:{data:string})=>void)|null=null;onerror:(()=>void)|null=null;onclose:(()=>void)|null=null;send=vi.fn();close=vi.fn();constructor(){instance=this;}}
    vi.stubGlobal('WebSocket',FakeSocket);
    render(<LivePage settings={defaultSettings} online={true} modelReady={true}/>);
    const video=screen.getByLabelText('Live camera preview');
    Object.defineProperties(video,{readyState:{value:4},videoWidth:{value:960},videoHeight:{value:540}});
    fireEvent.click(screen.getByRole('checkbox',{name:/I have permission/}));fireEvent.click(screen.getByRole('button',{name:'Start live feed'}));
    await waitFor(()=>expect(instance!).toBeTruthy());
    instance!.onopen!();
    expect(JSON.parse(instance!.send.mock.calls[0][0]).options.processing_consent).toBe(true);
    const {act}=await import('@testing-library/react');
    await act(async()=>{instance!.onmessage!({data:JSON.stringify({type:'ready'})});});
    expect(screen.getByText('LIVE TRACKING')).toBeTruthy();
    expect(instance!.send.mock.calls.length).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole('button',{name:'Stop live feed'}));
    expect(stopTrack).toHaveBeenCalledOnce();expect(instance!.close).toHaveBeenCalledOnce();
    expect(screen.getByText('CAMERA OFF')).toBeTruthy();
  });
  it('requires permission attestation before starting',()=>{
    render(<LivePage settings={defaultSettings} online={true} modelReady={true}/>);
    expect((screen.getByRole('button',{name:'Start live feed'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox',{name:/I have permission/}));
    expect((screen.getByRole('button',{name:'Start live feed'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('does not try to access a camera while offline',()=>{
    render(<LivePage settings={defaultSettings} online={false} modelReady={false}/>);
    fireEvent.click(screen.getByRole('checkbox',{name:/I have permission/}));
    expect((screen.getByRole('button',{name:'Start live feed'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('explains secure context requirements without pretending the camera is live',async()=>{
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:undefined});
    render(<LivePage settings={defaultSettings} online={true} modelReady={true}/>);
    fireEvent.click(screen.getByRole('checkbox',{name:/I have permission/}));
    fireEvent.click(screen.getByRole('button',{name:'Start live feed'}));
    expect((await screen.findByRole('alert')).textContent).toContain('HTTPS');
    expect(screen.getByText('CAMERA OFF')).toBeTruthy();
  });
  it('handles denied browser permission and keeps the camera off',async()=>{
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:vi.fn().mockRejectedValue(new DOMException('Denied','NotAllowedError'))}});
    render(<LivePage settings={defaultSettings} online={true} modelReady={true}/>);
    fireEvent.click(screen.getByRole('checkbox',{name:/I have permission/}));
    fireEvent.click(screen.getByRole('button',{name:'Start live feed'}));
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('Camera permission was denied'));
    expect(screen.getByText('CAMERA OFF')).toBeTruthy();
  });
  it('requires guardian consent and player assent when juniors appear',async()=>{
    render(<LivePage settings={defaultSettings} online={true} modelReady={true}/>);
    fireEvent.click(screen.getByRole('checkbox',{name:/I have permission/}));
    fireEvent.click(screen.getByRole('checkbox',{name:'A junior player is in the camera view.'}));
    expect(screen.getByLabelText('Consenting guardian’s name')).toBeTruthy();
    expect(screen.getByRole('checkbox',{name:'Junior agrees to live analysis.'})).toBeTruthy();
  });
  it('builds WebSocket endpoints without putting tokens in URLs',()=>{
    expect(liveSocketUrl()).toContain('/api/live');
    expect(liveSocketUrl()).not.toContain('token');
    expect(ratingLabel(null)).toContain('Waiting');
    expect(ratingLabel(90)).toContain('Mostly');
    expect(ratingLabel(60)).toContain('Mixed');
    expect(ratingLabel(20)).toContain('coach');
  });
});
