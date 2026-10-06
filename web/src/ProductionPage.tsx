import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Circle, FlaskConical, LoaderCircle, RotateCcw, ShieldCheck } from 'lucide-react';
import { request } from './api';
import { PageTitle } from './components';

interface Gate { id: string; label: string; passed: boolean; detail: string }
interface Status {
  release_ready: boolean;
  gates: Gate[];
  training: {
    ready: boolean;
    errors: string[];
    splits: Record<string, {
      ready: boolean;
      sessions?: number;
      shots?: number;
      classes?: Record<string, number>;
      message?: string;
    }>;
  };
}

export default function ProductionPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try { setStatus(await request<Status>('/production')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not load release checks.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <>
    <PageTitle eyebrow="WORKSPACE / RELEASE CHECKS" title="Production readiness"
      description="Review the evidence required for a real court pilot."/>
    {loading ? <div className="panel page-loading" role="status"><LoaderCircle size={20} className="spin"/>Loading release checks…</div>
      : error ? <section className="panel page-error" role="alert"><AlertCircle size={24}/><h2>Release checks are unavailable</h2><p>{error}</p>
        <button className="secondary-button" onClick={() => void load()}><RotateCcw size={15}/>Try again</button></section>
      : status && <>
        <div className="production-intro panel"><ShieldCheck/><div>
          <h2>{status.release_ready ? 'Release evidence checks passed' : 'Preparing for a real court pilot'}</h2>
          <p>Software checks verify behavior. Independent labels, coach reviews and camera trials verify coaching quality.</p>
        </div><strong>{status.gates.filter(gate => gate.passed).length}<small> / {status.gates.length} gates</small></strong></div>
        <div className="production-grid">{status.gates.map(gate =>
          <section className={'panel production-gate ' + (gate.passed ? 'passed' : '')} key={gate.id}>
            {gate.passed ? <CheckCircle2/> : <Circle/>}<span className="eyebrow">{gate.passed ? 'VERIFIED' : 'EVIDENCE REQUIRED'}</span>
            <h2>{gate.label}</h2><p>{gate.detail}</p>
          </section>)}</div>
        <section className="panel training-panel">
          <div className="panel-heading"><div><span className="eyebrow">REAL SAMPLES, REVIEWED LABELS</span><h2><FlaskConical size={18}/>Tennis model training</h2></div>
            <span className="small-badge">{status.training.ready ? 'Data checks passed' : 'Waiting for training data'}</span></div>
          <p>Training requires separate permission from every player and an independent test set. Synthetic demos do not qualify.</p>
          <div className="training-splits">{Object.entries(status.training.splits).map(([name, split]) =>
            <div key={name}><strong>{name}</strong><span>{split.sessions ?? 0} sessions · {split.shots ?? 0} reviewed shots</span>
              <small>{split.ready ? 'Manifest verified' : split.message || 'Manifest requires review'}</small></div>)}</div>
          <details className="release-technical-details"><summary>Training setup details</summary>
            <p className="field-help">Prepare train.json, validation.json and test.json in data/labels. Training checks consent, file hashes and player/session separation before fitting. Candidate models must pass held-out promotion checks before use.</p>
          </details>
        </section>
      </>}
  </>;
}
