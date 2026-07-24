import type { Audience } from '@/hooks/useAudience';

export function AudienceSwitch({ audience, onChange }: {
  audience: Audience;
  onChange: (a: Audience) => void;
}) {
  return (
    <div className="audience-switch" role="tablist" aria-label="Selettore area">
      <button
        role="tab"
        aria-selected={audience === 'public'}
        className={`audience-switch__btn${audience === 'public' ? ' audience-switch__btn--active' : ''}`}
        onClick={() => onChange('public')}
      >
        Area pubblica
      </button>
      <button
        role="tab"
        aria-selected={audience === 'researcher'}
        className={`audience-switch__btn${audience === 'researcher' ? ' audience-switch__btn--active' : ''}`}
        onClick={() => onChange('researcher')}
      >
        Area ricercatore
      </button>
    </div>
  );
}
