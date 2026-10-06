import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import LiveShotAssessment from './LiveShotAssessment';
import type { LiveShot } from './live';

const candidate: LiveShot = {
  id: 'live-1', player_id: 'player-near', type: 'forehand', start: 0, contact: 1, end: 2,
  confidence: .78, classification_source: 'heuristic', classification_evidence: ['Wrist on the hitting-arm side'],
  rating: 50, experimental: true, metrics: [], tips: [], technique: {
    status: 'provisional', score: 50, measured_checks: 2, expected_checks: 2, rule_version: 'hypothesis-1',
    explanation: 'Percentage of measured checks within configured ranges.', checks: [
      { metric: 'knee_angle', label: 'Knee bend', phase: 'preparation', value: 140, unit: '°', target: [105, 160], status: 'within_target', reason: null },
      { metric: 'finish_height', label: 'Finish height', phase: 'finish', value: .4, unit: '× torso', target: [.7, 1.8], status: 'below_target', reason: null }
    ]
  }
};

describe('live shot evidence', () => {
  it('separates classification confidence from the phase-based technique score', () => {
    render(<LiveShotAssessment shot={candidate} coachValidated={false}/>);
    expect(screen.getByText('Forehand candidate')).toBeTruthy();
    expect(screen.getByText(/78% detection confidence/)).toBeTruthy();
    expect(screen.getByText(/not a measured accuracy rate/)).toBeTruthy();
    expect(screen.getByText(/2 of 2 technique checks measured/)).toBeTruthy();
    expect(screen.getByText('Within target')).toBeTruthy();
    expect(screen.getByText('Below target')).toBeTruthy();
    expect(screen.getByText('Preparation')).toBeTruthy();
    expect(screen.getByText(/await coach validation/)).toBeTruthy();
  });
  it('explains incomplete evidence instead of reporting a good shot', () => {
    const partial: LiveShot = { ...candidate, rating: null, technique: { ...candidate.technique!, score: null, status: 'limited', measured_checks: 1,
      explanation: 'Only 1 of 2 technique checks are measurable; no overall score.' } };
    render(<LiveShotAssessment shot={partial} coachValidated={false}/>);
    expect(screen.getByText('No overall score yet')).toBeTruthy();
    expect(screen.getByText(/Only 1 of 2/)).toBeTruthy();
    expect(screen.queryByText(/No measured out-of-range finding/)).toBeNull();
  });
  it('names ambiguous shots explicitly and handles the initial camera state', () => {
    const { rerender } = render(<LiveShotAssessment shot={{ ...candidate, type: 'unknown', rating: null, technique: null }} coachValidated={false}/>);
    expect(screen.getByText('Uncertain shot')).toBeTruthy();
    rerender(<LiveShotAssessment shot={null} coachValidated={false}/>);
    expect(screen.getByText('Your latest shot')).toBeTruthy();
    expect(screen.getByText(/first swing and follow-through/)).toBeTruthy();
  });
  it('suppresses technique comparisons when experimental coaching is disabled', () => {
    const disabled: LiveShot = { ...candidate, rating: null, technique: { ...candidate.technique!, status: 'disabled', score: null,
      explanation: 'Enable experimental coaching to compare measured technique.' } };
    render(<LiveShotAssessment shot={disabled} coachValidated={false}/>);
    expect(screen.getByText(/Enable experimental coaching/)).toBeTruthy();
    expect(screen.queryByLabelText('Technique checks')).toBeNull();
    expect(screen.queryByText('Within target')).toBeNull();
  });
});
