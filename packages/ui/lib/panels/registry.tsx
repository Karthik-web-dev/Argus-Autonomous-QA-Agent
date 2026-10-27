import type { ComponentType } from "react";

export interface PanelProps {
  runId: string;
}

export interface PanelRegistration {
  id: string;
  title: string;
  component: ComponentType<PanelProps>;
}

const panels = new Map<string, PanelRegistration>();

export function registerPanel(panel: PanelRegistration): void {
  if (!panel.id.trim()) throw new Error("Panel id cannot be empty.");
  panels.set(panel.id, panel);
}

export function getPanels(): PanelRegistration[] {
  return [...panels.values()];
}

export function getPanel(id: string): PanelRegistration | undefined {
  return panels.get(id);
}
