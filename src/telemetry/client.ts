import * as vscode from 'vscode';

export const TELEMETRY_ENDPOINT = 'http://127.0.0.1:8000/telemetry';

export type CognitiveState = 'FLOW' | 'NORMAL' | 'OVERLOADED';

export interface TelemetryPayload {
  backspaceCount: number;
  fileSwitchCount: number;
  errorCount: number;
  activeFile?: string;
  snippet?: string;
  diagnostics?: string[];
  semanticTrigger?: string;
}

export interface Diagnosis {
  trigger: string;
  root_cause: string;
  patch: string;
  patch_code: string;
  confidence: number;
}

export interface TelemetryResponse {
  score: number;
  state: CognitiveState;
  diagnosis?: Diagnosis;
}

export function buildPayload(
  backspaceCount: number,
  fileSwitchCount: number,
  errorCount: number,
  semanticTrigger: string | undefined,
  outputChannel: vscode.OutputChannel,
): TelemetryPayload {
  const editor = vscode.window.activeTextEditor;

  const snippet = getCodeSnippet(editor);
  const diagnostics = getActiveFileDiagnostics(editor);

  outputChannel.appendLine(
    `[FlowGuard] ${new Date().toISOString()} — ` +
      `backspaces=${backspaceCount} switches=${fileSwitchCount} errors=${errorCount}` +
      (semanticTrigger ? ` semantic="${semanticTrigger}"` : ''),
  );

  return {
    backspaceCount,
    fileSwitchCount,
    errorCount,
    activeFile: editor?.document.fileName,
    snippet,
    diagnostics,
    semanticTrigger,
  };
}

export async function sendTelemetry(
  payload: TelemetryPayload,
  outputChannel: vscode.OutputChannel,
): Promise<TelemetryResponse | undefined> {
  try {
    const response = await fetch(TELEMETRY_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`backend responded with ${response.status}`);
    }
    return (await response.json()) as TelemetryResponse;
  } catch (error) {
    outputChannel.appendLine(`[FlowGuard] Telemetry POST failed: ${String(error)}`);
    return undefined;
  }
}

function getCodeSnippet(editor: vscode.TextEditor | undefined): string | undefined {
  if (!editor) {
    return undefined;
  }
  const doc = editor.document;
  const cursor = editor.selection.active;
  const start = Math.max(0, cursor.line - 15);
  const end = Math.min(doc.lineCount - 1, cursor.line + 15);
  const lines: string[] = [];
  for (let i = start; i <= end; i++) {
    lines.push(`${i === cursor.line ? '→' : ' '} ${doc.lineAt(i).text}`);
  }
  return lines.join('\n');
}

function getActiveFileDiagnostics(editor: vscode.TextEditor | undefined): string[] {
  if (!editor) {
    return [];
  }
  return vscode.languages
    .getDiagnostics(editor.document.uri)
    .filter((d) => d.severity === vscode.DiagnosticSeverity.Error)
    .slice(0, 5)
    .map((d) => d.message);
}
