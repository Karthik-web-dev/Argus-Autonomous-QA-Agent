import { benchmarkApps, landingCopy } from "@/lib/landing-content";
export function LogoBar() { return <div className="logo-bar wrap" id="benchmark"><span>{landingCopy.benchmark.title}</span><div className="logo-list">{benchmarkApps.map((name, i) => <span key={name} className={`text-mark mark-${i}`}>{name}</span>)}</div></div>; }
