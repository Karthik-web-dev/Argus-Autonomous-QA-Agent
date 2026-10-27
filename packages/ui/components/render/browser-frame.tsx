export function BrowserFrame({ image, alt = "Browser capture" }: { image: string; alt?: string }) {
  return <figure><img src={image} alt={alt} style={{ display: "block", width: "100%", borderRadius: 8 }} /></figure>;
}
