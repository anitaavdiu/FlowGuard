import * as vscode from 'vscode';

const LOG_INTERVAL_MS = 60_000;
const TELEMETRY_ENDPOINT = 'http://127.0.0.1:8000/telemetry';

type CognitiveState = 'FLOW' | 'NORMAL' | 'OVERLOADED';

interface WindowMetrics {
  backspaceCount: number;
  fileSwitchCount: number;
}

interface TelemetryPayload {
  backspaceCount: number;
  fileSwitchCount: number;
  errorCount: number;
}

interface TelemetryResponse {
  score: number;
  state: CognitiveState;
}

let metrics: WindowMetrics = { backspaceCount: 0, fileSwitchCount: 0 };
let logTimer: ReturnType<typeof setInterval> | undefined;
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;
let lastState: CognitiveState | undefined;

function isDeletion(change: vscode.TextDocumentContentChangeEvent): boolean {
  return change.text.length === 0 && change.rangeLength > 0;
}

function countTotalDiagnostics(): { errors: number; warnings: number } {
  let errors = 0;
  let warnings = 0;
  for (const [, diagnostics] of vscode.languages.getDiagnostics()) {
    for (const diagnostic of diagnostics) {
      if (diagnostic.severity === vscode.DiagnosticSeverity.Error) {
        errors++;
      } else if (diagnostic.severity === vscode.DiagnosticSeverity.Warning) {
        warnings++;
      }
    }
  }
  return { errors, warnings };
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

function updateStatusBar(state: CognitiveState, score: number): void {
  const display = STATE_DISPLAY[state];
  statusBarItem.text = `${display.icon} FlowGuard: ${display.label}`;
  statusBarItem.tooltip = `Cognitive load score: ${score.toFixed(1)} / 100`;
  statusBarItem.backgroundColor = display.background;
  statusBarItem.show();
}

// Stand-in for a real Anthropic API call. Swap the body of this function for an
// `anthropic.messages.create(...)` request (reading the API key from an env var
// or vscode SecretStorage) when a live agent connection is wanted.
const STEP_DOWN_HINTS = [
  'Take a 2-minute break — step away from the keyboard and look away from the screen.',
  "Close extra tabs/files and focus on just the one you're editing.",
  'Re-read the last error message slowly before making another change.',
  'Try explaining the bug out loud, as if to a colleague, before touching the code again.',
  'Save your progress and take a short walk — the fix will still be there in 5 minutes.',
];

async function fetchStepDownHint(): Promise<string> {
  return STEP_DOWN_HINTS[Math.floor(Math.random() * STEP_DOWN_HINTS.length)];
}

async function handleOverloadTransition(): Promise<void> {
  try {
    const hint = await fetchStepDownHint();
    outputChannel.appendLine(`[FlowGuard] Step-down hint: ${hint}`);
    void vscode.window.showWarningMessage(`FlowGuard: You seem overloaded. ${hint}`);
  } catch (error) {
    outputChannel.appendLine(`[FlowGuard] Failed to fetch step-down hint: ${String(error)}`);
  }
}

async function sendTelemetry(payload: TelemetryPayload): Promise<TelemetryResponse | undefined> {
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

async function logMetrics(): Promise<void> {
  const { errors, warnings } = countTotalDiagnostics();
  const payload: TelemetryPayload = {
    backspaceCount: metrics.backspaceCount,
    fileSwitchCount: metrics.fileSwitchCount,
    errorCount: errors,
  };

  console.log(
    '[FlowGuard]',
    JSON.stringify({
      timestamp: new Date().toISOString(),
      backspacesPerMinute: payload.backspaceCount,
      fileSwitchesPerMinute: payload.fileSwitchCount,
      workspaceErrors: errors,
      workspaceWarnings: warnings,
    }),
  );

  metrics = { backspaceCount: 0, fileSwitchCount: 0 };

  const result = await sendTelemetry(payload);
  if (!result) {
    return;
  }

  outputChannel.appendLine(`[FlowGuard] score=${result.score.toFixed(1)} state=${result.state}`);
  updateStatusBar(result.state, result.score);

  if (result.state === 'OVERLOADED' && lastState !== 'OVERLOADED') {
    await handleOverloadTransition();
  }
  lastState = result.state;
}

export function activate(context: vscode.ExtensionContext): void {
  console.log('[FlowGuard] activated');

  outputChannel = vscode.window.createOutputChannel('FlowGuard');

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = `${STATE_DISPLAY.NORMAL.icon} FlowGuard: Normal`;
  statusBarItem.show();

  const textChangeListener = vscode.workspace.onDidChangeTextDocument((event) => {
    for (const change of event.contentChanges) {
      if (isDeletion(change)) {
        metrics.backspaceCount++;
      }
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
