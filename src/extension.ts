import * as vscode from 'vscode';

import { SemanticAnalyzer } from './analysis/semanticAnalyzer';
import {
  buildPayload,
  CognitiveState,
  Diagnosis,
  sendTelemetry,
} from './telemetry/client';
import {
  clearPendingPatch,
  FlowGuardPatchProvider,
  initPatchProvider,
  registerPatchCommand,
  setPendingPatch,
} from './utils/patchProvider';

const LOG_INTERVAL_MS = 60_000;

interface WindowMetrics {
  backspaceCount: number;
  fileSwitchCount: number;
}

const STATE_DISPLAY: Record<
  CognitiveState,
  { label: string; icon: string; background?: vscode.ThemeColor }
> = {
  FLOW: { label: 'Flow', icon: '$(zap)' },
  NORMAL: { label: 'Normal', icon: '$(circle-outline)' },
  OVERLOADED: {
    label: 'Overloaded',
    icon: '$(flame)',
    background: new vscode.ThemeColor('statusBarItem.errorBackground'),
  },
};

let metrics: WindowMetrics = { backspaceCount: 0, fileSwitchCount: 0 };
let logTimer: ReturnType<typeof setInterval> | undefined;
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;
let lastState: CognitiveState | undefined;
const semanticAnalyzer = new SemanticAnalyzer();

function isDeletion(change: vscode.TextDocumentContentChangeEvent): boolean {
  return change.text.length === 0 && change.rangeLength > 0;
}

function countTotalDiagnostics(): { errors: number; warnings: number } {
  let errors = 0;
  let warnings = 0;
  for (const [, diagnostics] of vscode.languages.getDiagnostics()) {
    for (const d of diagnostics) {
      if (d.severity === vscode.DiagnosticSeverity.Error) errors++;
      else if (d.severity === vscode.DiagnosticSeverity.Warning) warnings++;
    }
  }
  return { errors, warnings };
}

function updateStatusBar(state: CognitiveState, score: number): void {
  const display = STATE_DISPLAY[state];
  statusBarItem.text = `${display.icon} FlowGuard: ${display.label}`;
  statusBarItem.tooltip = `Cognitive load score: ${score.toFixed(1)} / 100`;
  statusBarItem.backgroundColor = display.background;
  statusBarItem.show();
}

function handleOverloadTransition(diagnosis: Diagnosis | undefined): void {
  if (diagnosis) {
    const pct = (diagnosis.confidence * 100).toFixed(0);
    const message = `FlowGuard: ${diagnosis.trigger} — ${diagnosis.patch} (${pct}% confidence)`;
    outputChannel.appendLine(`[FlowGuard] Diagnosis: ${JSON.stringify(diagnosis)}`);
    void vscode.window.showWarningMessage(message);
  } else {
    outputChannel.appendLine(
      '[FlowGuard] OVERLOADED — no diagnosis available (check ANTHROPIC_API_KEY)',
    );
    void vscode.window.showWarningMessage(
      'FlowGuard: cognitive overload detected. Consider a short break.',
    );
  }
}

async function logMetrics(): Promise<void> {
  const { errors } = countTotalDiagnostics();
  const editor = vscode.window.activeTextEditor;

  const payload = buildPayload(
    metrics.backspaceCount,
    metrics.fileSwitchCount,
    errors,
    semanticAnalyzer.getSemanticTrigger(
      editor ? getSnippetText(editor) : undefined,
    ),
    outputChannel,
  );

  metrics = { backspaceCount: 0, fileSwitchCount: 0 };

  const result = await sendTelemetry(payload, outputChannel);
  if (!result) {
    return;
  }

  outputChannel.appendLine(`[FlowGuard] score=${result.score.toFixed(1)} state=${result.state}`);
  updateStatusBar(result.state, result.score);

  if (result.state === 'OVERLOADED' && lastState !== 'OVERLOADED') {
    handleOverloadTransition(result.diagnosis);

    if (result.diagnosis?.patch_code && editor) {
      const cursor = editor.selection.active;
      setPendingPatch(
        editor.document.uri,
        cursor.line,
        result.diagnosis.patch_code,
        result.diagnosis.trigger,
      );
    }
  }

  if (result.state !== 'OVERLOADED') {
    clearPendingPatch();
  }

  lastState = result.state;
}

// Returns the raw text of the snippet window around the cursor, without the
// arrow markers, so the semantic analyzer can count brackets correctly.
function getSnippetText(editor: vscode.TextEditor): string {
  const doc = editor.document;
  const cursor = editor.selection.active;
  const start = Math.max(0, cursor.line - 15);
  const end = Math.min(doc.lineCount - 1, cursor.line + 15);
  const lines: string[] = [];
  for (let i = start; i <= end; i++) {
    lines.push(doc.lineAt(i).text);
  }
  return lines.join('\n');
}

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel('FlowGuard');
  outputChannel.appendLine('[FlowGuard] activated');

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = `${STATE_DISPLAY.NORMAL.icon} FlowGuard: Normal`;
  statusBarItem.show();

  initPatchProvider(context);
  registerPatchCommand(context);

  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      { scheme: 'file' },
      new FlowGuardPatchProvider(),
      { providedCodeActionKinds: FlowGuardPatchProvider.providedCodeActionKinds },
    ),
  );

  const textChangeListener = vscode.workspace.onDidChangeTextDocument((event) => {
    for (const change of event.contentChanges) {
      const del = isDeletion(change);
      if (del) {
        metrics.backspaceCount++;
      }
      semanticAnalyzer.recordEdit(change.range.start.line, del);
    }
  });

  const editorChangeListener = vscode.window.onDidChangeActiveTextEditor((editor) => {
    if (editor) {
      metrics.fileSwitchCount++;
    }
  });

  logTimer = setInterval(() => {
    void logMetrics();
  }, LOG_INTERVAL_MS);

  context.subscriptions.push(
    textChangeListener,
    editorChangeListener,
    statusBarItem,
    outputChannel,
    { dispose: () => clearInterval(logTimer) },
  );
}

export function deactivate(): void {
  if (logTimer) {
    clearInterval(logTimer);
  }
}
