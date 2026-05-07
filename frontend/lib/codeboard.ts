import type { IssueType } from '@/types/codeboard';

export type ExecutableIssueType = 'TASK' | 'SUBTASK' | 'BUG';

export const EXECUTABLE_TYPES: readonly ExecutableIssueType[] = ['TASK', 'SUBTASK', 'BUG'] as const;

export function isExecutableType(t: IssueType): t is ExecutableIssueType {
  return EXECUTABLE_TYPES.includes(t as ExecutableIssueType);
}
