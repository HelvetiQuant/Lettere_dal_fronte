import type { ReactNode } from 'react';

export function PageIntro({ title, description, aiNote, steps }: {
  title: string;
  description: string;
  aiNote?: string;
  steps?: string[];
}) {
  return (
    <div className="page-intro">
      <h1 className="page-intro__title">{title}</h1>
      <p className="page-intro__desc">{description}</p>
      {aiNote && (
        <div className="page-intro__ai">
          <strong>Come interviene l'IA:</strong> {aiNote}
        </div>
      )}
      {steps && steps.length > 0 && (
        <div className="howto">
          {steps.map((step, i) => (
            <div key={i} className="howto__step">
              <div className="howto__step-num">{i + 1}</div>
              {step}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Section({ title, action, children }: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="section">
      {(title || action) && (
        <div className="section__header">
          {title && <h2>{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
