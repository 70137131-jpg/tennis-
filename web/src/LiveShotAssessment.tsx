import { Activity, ShieldCheck, Target } from 'lucide-react';
import { capitalize } from './components';
import { ratingLabel, type LiveShot } from './live';
import type { TechniqueCheck } from './types';

const checkLabels: Record<TechniqueCheck['status'], string> = {
  within_target: 'Within target', below_target: 'Below target', above_target: 'Above target',
  not_measurable: 'Not measurable', no_target: 'No target yet'
};

export default function LiveShotAssessment({ shot, coachValidated }: { shot: LiveShot | null; coachValidated: boolean }) {
  const assessment = shot?.technique;
  const score = assessment ? assessment.score : shot?.rating ?? null;
  const title = !shot ? 'Your latest shot' : shot.type === 'unknown' ? 'Uncertain shot' : `${capitalize(shot.type)} candidate`;
  return <section className="panel live-insight" aria-label="Latest shot assessment">
    <div className="setup-heading"><span className="section-number">02</span><div><span className="eyebrow">SHOT TYPE & TECHNIQUE</span><h2>{title}</h2></div><Target size={19}/></div>
    {shot && <div className="live-classification">
      <strong>{shot.player_id === 'player-far' ? 'Far player' : 'Near player'} · {Math.round(shot.confidence * 100)}% detection confidence</strong>
      <p>{shot.classification_source === 'trained' ? 'Temporal pose classifier' : 'Movement-based estimate'} · confidence is not a measured accuracy rate.</p>
      {!!shot.classification_evidence?.length && <ul>{shot.classification_evidence.map(evidence => <li key={evidence}>{evidence}</li>)}</ul>}
    </div>}
    <div className="live-score"><strong>{score ?? '—'}<small>{score !== null ? '%' : ''}</small></strong><span>{score !== null ? 'Technique target match' : 'No overall score yet'}</span></div>
    <p>{assessment?.explanation || ratingLabel(score)}</p>
    {assessment && assessment.status !== 'disabled' && assessment.expected_checks > 0 && <p className="live-evidence-count">{assessment.measured_checks} of {assessment.expected_checks} technique checks measured · Rule {assessment.rule_version}</p>}
    {assessment?.checks.length && assessment.status !== 'disabled' ? <div className="live-technique-checks" aria-label="Technique checks">{assessment.checks.map(check => <div className={`live-technique-check ${check.status}`} key={`${check.metric}-${check.phase}`}>
      <div><strong>{check.label}</strong><small>{capitalize(check.phase)}</small><span>{checkLabels[check.status]}</span></div>
      <p>{check.value === null ? check.reason : <>{check.value}{check.unit}{check.target ? ` · target ${check.target.join('–')}${check.unit}` : ` · ${check.reason}`}</>}</p>
    </div>)}</div> : shot?.metrics.filter(metric => metric.measurable).map(metric => <div className="live-metric" key={metric.name}><span>{metric.label}</span><strong>{metric.value}{metric.unit}</strong></div>)}
    {shot?.tips.length ? shot.tips.map(tip => <div className="live-tip" key={tip.id}><Target size={16}/><div><h3>{tip.title}</h3><p>{tip.explanation}</p><small>{tip.metric.replaceAll('_', ' ')}: {tip.value} · target {tip.target.join('–')}</small></div></div>)
      : <div className="live-tip"><Activity size={17}/><p>{!shot ? 'Measurements appear after your first swing and follow-through.' : score === null ? 'More evidence is needed before an overall technique assessment.' : 'Review the measured checks above with your coach.'}</p></div>}
    <div className="live-experimental"><ShieldCheck size={14}/><span>{coachValidated ? 'Coach-approved rule thresholds' : 'Experimental technique targets await coach validation.'}</span></div>
  </section>;
}
