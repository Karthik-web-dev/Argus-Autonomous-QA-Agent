export function MessageList({ messages }: { messages: { role: string; content: string }[] }) {
  return <ol>{messages.map((message, index) => <li key={index}><strong>{message.role}</strong>: {message.content}</li>)}</ol>;
}
