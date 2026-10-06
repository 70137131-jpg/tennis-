import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Modal, scoreFor, Status, TrendChart } from './components';
import { demoSessions } from './demo';
import type { Shot } from './types';
describe('evidence and accessible controls', () => {
  it('does not count unmeasurable or missing-target metrics as technique findings', () => {
    const base = demoSessions()[0].report!.shots[0];
    const metric = { name:'knee_angle', label:'Knee bend', phase:'contact', value:130, confidence:.9, measurable:true, unit:'deg', target:[110,160] };
    const shots = [{...base, metrics:[metric]}, {...base, metrics:[{...metric, value:175}]}, {...base, metrics:[{...metric, measurable:false, value:null}]}, {...base, metrics:[{...metric, target:undefined}]}] as Shot[];
    expect(scoreFor(shots)).toBe(50);
    expect(scoreFor([])).toBeNull();
  });
  it('shows an empty progress state when there is no evidence', () => {
    render(<TrendChart sessions={[]}/>);
    expect(screen.getByText('Your progress starts here')).toBeTruthy();
  });
  it.each([['queued','In queue'],['failed','Needs attention'],['processing','Analyzing · 37%'],['completed','Ready to review']] as const)('describes %s status', (status, label) => {
    render(<Status session={{...demoSessions()[0],status,progress:37}}/>);
    expect(screen.getByText(label)).toBeTruthy();
  });
  it('closes on Escape, traps focus and restores scrolling', () => {
    const close = vi.fn();
    const {unmount} = render(<Modal title="Upload" onClose={close}><button>First</button><button>Last</button></Modal>);
    expect(document.body.style.overflow).toBe('hidden');
    const last=screen.getByRole('button',{name:'Last'}); last.focus();
    fireEvent.keyDown(document,{key:'Tab'});
    expect(document.activeElement).toBe(screen.getByRole('button',{name:'Close dialog'}));
    fireEvent.keyDown(document,{key:'Escape'});
    expect(close).toHaveBeenCalledOnce();
    unmount(); expect(document.body.style.overflow).toBe('');
  });
});

