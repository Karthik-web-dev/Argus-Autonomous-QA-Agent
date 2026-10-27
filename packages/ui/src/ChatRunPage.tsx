import { LiveView } from "@/components/live-view";

export default function ChatRunPage({ id }: { id: string }) {
  return <main className="shell"><p className="eyebrow">Run workspace</p><h1>QA run {id}</h1><p className="lede">Live Chromium frames and action cues are streamed from the isolated browser session.</p><LiveView runId={id}/></main>;
}
