import { landingCopy, trustRows } from "@/lib/landing-content";

export function TrustSection() {
  const c = landingCopy.trust;
  return <section className="section wrap" id="trust">
    <div className="section-intro"><h2>{c.title}<br/>{c.titleLineTwo}</h2><p>{c.description}</p></div>
    <div className="trust-panel">
      <div className="trust-col"><div className="panel-label"><b/> {c.evidenceLabel}<small>{c.sampleData}</small></div><div className="evidence-card">
        <h3>{c.replayTitle}</h3><div className="check-row">{[0,1,2,3,4].map((x)=><span className={x===4?"last-check":""} key={x}>✓</span>)}</div>
        <p className="replay-success"><span className="dot green"/> {c.reproduced}</p><button className="button button-cream view-button">{c.evidenceAction}</button><small className="locked-copy">⌑ {c.deterministic}</small>
      </div></div>
      <div className="trust-col"><div className="panel-label"><b className="gold-dot"/> {c.redTeamLabel}</div><div className="redteam-card">
        <header><div><small>{c.verificationRun}</small><strong>{c.sampleBug}</strong></div><span className="confirmed">{c.confirmed}</span></header>
        {trustRows.map(([icon,label,state],i)=><div className={`verify-row ${i===3?"verifying":""}`} key={label}><span className="verify-icon">{icon}</span><strong>{label}</strong><span className={i===3?"state-running":"state-confirmed"}>{state}</span></div>)}
      </div></div>
    </div>
    <div className="trust-captions">
      <article><div className="caption-art mini-form"><label>{c.passwordLabel}</label><div className="masked">{c.passwordField}</div><button>{c.verifyAction}</button></div><h3>{c.captions[0].title}</h3><p>{c.captions[0].description}</p></article>
      <article><div className="caption-art vault-art">{c.vaultRows.map(x=><div className="vault-row" key={x}><span>◈</span><b>{c.password}</b><i>⌑</i></div>)}</div><h3>{c.captions[1].title}</h3><p>{c.captions[1].description}</p></article>
      <article><div className="caption-art network-art"><b>{c.traceStatus}</b><span>{c.traceRequest}</span><small>{c.traceLabel}</small></div><h3>{c.captions[2].title}</h3><p>{c.captions[2].description}</p></article>
    </div>
  </section>;
}
