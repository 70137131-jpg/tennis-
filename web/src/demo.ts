import type { Session, Settings, Shot, Tip } from './types';
export const defaultSettings: Settings = { display_name: 'Ali', player_name: 'Ali Haider', handedness: 'right', backhand_style: 'two-handed', level: 'competitive', retention_days: 30, blur_faces: true };
export function demoSessions(): Session[] {
  return ['Baseline practice', 'Serve & return', 'Evening rally', 'Match day', 'Footwork & forehands', 'Sunday on court'].map((title, index) => {
    const shots: Shot[] = Array.from({ length: [48, 36, 54, 64, 42, 40][index] }, (_, i) => {
      const type = (['forehand', 'backhand', 'forehand', 'serve', 'volley', 'forehand', 'backhand', 'serve'] as const)[i % 8];
      const knee = 137 + (i * 7 + index * 4) % 35; const elbow = 143 + (i * 3) % 35; const height = .58 + i % 10 / 10;
      const tips: Tip[] = [];
      if (type === 'serve' && elbow < 145) tips.push({ id: 'elbow_extension-contact', metric: 'elbow_extension', value: elbow, target: [145, 180], severity: 3, title: 'Reach through your serve', explanation: 'Aim for a relaxed, extended hitting arm at contact. Review your motion with your coach.', rule_version: 'synthetic-demo-1' });
      if (knee > 160 && type !== 'volley') tips.push({ id: 'knee_angle-preparation', metric: 'knee_angle', value: knee, target: [110, 160], severity: 2, title: 'Give your legs a little more room', explanation: 'Try a comfortable knee bend as you prepare. Review this camera-angle-dependent measurement with your coach.', rule_version: 'synthetic-demo-1' });
      if (height < .7 && ['forehand', 'backhand'].includes(type)) tips.push({ id: 'finish_height-finish', metric: 'finish_height', value: Number(height.toFixed(2)), target: [.7, 1.8], severity: 1, title: 'Let the swing finish', explanation: 'Allow your hitting hand to finish higher after contact. This is a wrist-height proxy.', rule_version: 'synthetic-demo-1' });
      return { id: `shot-${String(i + 1).padStart(4, '0')}`, player_id: 'player-near', type, start: 16.8 + i * 22, contact: 18 + i * 22, end: 19.5 + i * 22, confidence: .87 + i % 7 * .015, tips,
        metrics: [{ name: 'knee_angle', label: 'Knee bend', phase: 'preparation', value: knee, unit: '°', confidence: .93, measurable: true, target: [110, 160] }, { name: 'elbow_extension', label: 'Arm extension', phase: 'contact', value: elbow, unit: '°', confidence: .94, measurable: true, target: [145, 180] }, { name: 'finish_height', label: 'Finish height', phase: 'finish', value: Number(height.toFixed(2)), unit: '× torso', confidence: .90, measurable: true, target: [.7, 1.8] }, { name: 'contact_in_front', label: 'Contact in front', phase: 'contact', value: null, unit: '', confidence: 0, measurable: false, reason: 'Not measurable from this 2D camera angle' }] };
    });
    const video = { width: 1920, height: 1080, fps: 60, duration: 1200 + index * 150, frames: 72000 };
    return { id: `demo-${index + 1}`, title, created_at: new Date(Date.now() - index * 3 * 86400000 - 7200000).toISOString(), status: 'completed', stage: 'Complete', progress: 100, is_demo: true, metadata: video,
      options: { player_name: 'Ali Haider', court: 'Court 01', session_type: index === 3 ? 'Match' : 'Practice', handedness: 'right', level: 'competitive' },
      report: { schema_version: '1.0.0', feedback_rules_version: 'synthetic-demo-1', coach_validated: false, video, shots, summary_tips: [...new Map(shots.flatMap(s => s.tips).map(t => [t.metric, t])).values()], warnings: ['Illustrative synthetic session. Metrics, tips and video are examples, not an analysis of a real player.'], annotated_video: 'demo.mp4', is_demo: true, diagnostics: {} } };
  });
}
