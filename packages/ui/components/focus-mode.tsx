
export function FocusMode({ children }: { children: React.ReactNode }) {
  return <section aria-label="Browser focus mode" style={{ position: "relative", overflow: "hidden", borderRadius: 12 }}>{children}</section>;
}
