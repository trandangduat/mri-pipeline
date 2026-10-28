export interface GpuSolution {
  title: string;
  instructions: string[];
  actionId: string | null;
  canExecute: boolean;
  unavailableReason: string;
  targetLabel: string;
  requiresAdmin: boolean;
  requiresDockerRestart: boolean;
}

export interface GpuSolutions {
  ticket: string;
  summary: string;
  code: string;
  solutions: GpuSolution[];
}

export interface GpuRepairState {
  ticket: string;
  busy: boolean;
  state: string;
  detail: string;
}

export function parseGpuSolutions(value: unknown): GpuSolutions | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const data = value as Record<string, unknown>;
  if (typeof data.ticket !== 'string' || typeof data.summary !== 'string' || !Array.isArray(data.solutions)) return undefined;
  const solutions = data.solutions.flatMap((item): GpuSolution[] => {
    if (!item || typeof item !== 'object') return [];
    const row = item as Record<string, unknown>;
    if (typeof row.title !== 'string') return [];
    const actionId = row.action_id === 'install_toolkit' || row.action_id === 'configure_runtime' ? row.action_id : null;
    return [{
      title: row.title,
      instructions: Array.isArray(row.instructions) ? row.instructions.filter((text): text is string => typeof text === 'string') : [],
      actionId,
      canExecute: row.can_execute === true && actionId !== null,
      unavailableReason: typeof row.unavailable_reason === 'string' ? row.unavailable_reason : '',
      targetLabel: typeof row.target_label === 'string' ? row.target_label : 'execution host',
      requiresAdmin: row.requires_admin === true,
      requiresDockerRestart: row.requires_docker_restart === true,
    }];
  });
  return {ticket: data.ticket, summary: data.summary, code: typeof data.code === 'string' ? data.code : '', solutions};
}
