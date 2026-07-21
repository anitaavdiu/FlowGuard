import * as vscode from 'vscode';

interface PendingPatch {
  fileUri: vscode.Uri;
  insertAfterLine: number;
  patchCode: string;
  trigger: string;
}

let pendingPatch: PendingPatch | undefined;
let diagnosticCollection: vscode.DiagnosticCollection;

// Must be called once during extension activation before any patch can be set.
export function initPatchProvider(context: vscode.ExtensionContext): void {
  diagnosticCollection = vscode.languages.createDiagnosticCollection('flowguard');
  context.subscriptions.push(diagnosticCollection);
}

// Stores a pending patch and places an info diagnostic at the target line so
// Ctrl+. (Quick Fix) surfaces the action in the editor gutter.
export function setPendingPatch(
  fileUri: vscode.Uri,
  insertAfterLine: number,
  patchCode: string,
  trigger: string,
): void {
  pendingPatch = { fileUri, insertAfterLine, patchCode, trigger };

  const range = new vscode.Range(insertAfterLine, 0, insertAfterLine, 0);
  const diag = new vscode.Diagnostic(
    range,
    `FlowGuard: ${trigger} — quick fix available (Ctrl+.)`,
    vscode.DiagnosticSeverity.Information,
  );
  diag.source = 'FlowGuard';
  diag.code = 'flowguard.patch';
  diagnosticCollection.set(fileUri, [diag]);
}

export function clearPendingPatch(): void {
  if (pendingPatch) {
    diagnosticCollection.delete(pendingPatch.fileUri);
  }
  pendingPatch = undefined;
}

export class FlowGuardPatchProvider implements vscode.CodeActionProvider {
  static readonly providedCodeActionKinds = [vscode.CodeActionKind.QuickFix];

  provideCodeActions(document: vscode.TextDocument): vscode.CodeAction[] {
    if (!pendingPatch || document.uri.fsPath !== pendingPatch.fileUri.fsPath) {
      return [];
    }

    const action = new vscode.CodeAction(
      `FlowGuard: apply suggested fix — ${pendingPatch.trigger}`,
      vscode.CodeActionKind.QuickFix,
    );
    action.command = {
      command: 'flowguard.applyPatch',
      title: 'Apply FlowGuard patch',
      arguments: [{ ...pendingPatch }],
    };
    action.isPreferred = true;
    return [action];
  }
}

export function registerPatchCommand(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'flowguard.applyPatch',
      async (patch: PendingPatch) => {
        const document = vscode.workspace.textDocuments.find(
          (d) => d.uri.fsPath === patch.fileUri.fsPath,
        );
        if (!document) {
          void vscode.window.showErrorMessage('FlowGuard: target file is no longer open.');
          return;
        }

        // Match the indentation of the line where we're inserting
        const targetLineIndex = Math.min(patch.insertAfterLine, document.lineCount - 1);
        const indent = document.lineAt(targetLineIndex).text.match(/^(\s*)/)?.[1] ?? '';
        const indentedCode = patch.patchCode
          .split('\n')
          .map((line) => (line.trim() ? indent + line : line))
          .join('\n');

        const edit = new vscode.WorkspaceEdit();
        edit.insert(patch.fileUri, new vscode.Position(patch.insertAfterLine + 1, 0), indentedCode + '\n');

        const ok = await vscode.workspace.applyEdit(edit);
        if (ok) {
          clearPendingPatch();
          void vscode.window.showInformationMessage(
            'FlowGuard: patch applied — review and adjust as needed.',
          );
        } else {
          void vscode.window.showErrorMessage('FlowGuard: could not apply patch.');
        }
      },
    ),
  );
}
