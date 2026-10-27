import { landingCopy, navigationLinks } from "@/lib/landing-content";
export function Nav() {
  return <nav className="nav wrap" aria-label="Main navigation"><a href="#top" className="brand" aria-label={landingCopy.nav.home}><img src="/logo/argus-wordmark.svg" alt="Argus" width={104} height={20} /></a><div className="nav-links">{navigationLinks.map(([label, href]) => <a key={label} href={href}>{label}</a>)}<span className="nav-divider" /><a href="/dashboard">{landingCopy.nav.signIn}</a><a href="/dashboard" className="button button-cream button-small">{landingCopy.nav.getStarted}</a></div><a href="/dashboard" className="button button-cream button-small mobile-start">{landingCopy.nav.getStarted}</a></nav>;
}
