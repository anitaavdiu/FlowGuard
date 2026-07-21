// Detects two patterns that naive backspace counting misses:
//   1. Edit thrash — the same 5-line region edited ≥4 times in 30s, with at
//      least half of those edits being deletions. This is the fingerprint of
//      someone stuck rewriting the same block.
//   2. Syntax imbalance — unmatched braces / parens / brackets inside the
//      cursor-adjacent snippet, indicating an incomplete or broken structure.
//      String contents are skipped to avoid false positives from template
//      literals, JSX attributes, and similar constructs.

interface EditEvent {
  line: number;
  timestamp: number;
  isDeletion: boolean;
}

const THRASH_WINDOW_MS = 30_000;
const THRASH_EDIT_THRESHOLD = 4;
const REGION_SIZE = 5;

export class SemanticAnalyzer {
  private editHistory: EditEvent[] = [];

  recordEdit(line: number, isDeletion: boolean): void {
    const now = Date.now();
    this.editHistory.push({ line, timestamp: now, isDeletion });
    // Drop anything outside the rolling window
    this.editHistory = this.editHistory.filter((e) => now - e.timestamp < THRASH_WINDOW_MS);
  }

  getThrashTrigger(): string | undefined {
    if (this.editHistory.length < THRASH_EDIT_THRESHOLD) {
      return undefined;
    }

    const regions = new Map<number, { total: number; deletions: number }>();
    for (const event of this.editHistory) {
      const key = Math.floor(event.line / REGION_SIZE) * REGION_SIZE;
      const bucket = regions.get(key) ?? { total: 0, deletions: 0 };
      bucket.total++;
      if (event.isDeletion) {
        bucket.deletions++;
      }
      regions.set(key, bucket);
    }

    for (const [startLine, counts] of regions) {
      if (
        counts.total >= THRASH_EDIT_THRESHOLD &&
        counts.deletions >= Math.ceil(counts.total / 2)
      ) {
        return (
          `edit thrash near line ${startLine + 1} ` +
          `(${counts.total} edits, ${counts.deletions} deletions in 30s)`
        );
      }
    }
    return undefined;
  }

  getSyntaxTrigger(snippet: string): string | undefined {
    let braces = 0;
    let parens = 0;
    let brackets = 0;
    let inString = false;
    let stringChar = '';

    for (let i = 0; i < snippet.length; i++) {
      const ch = snippet[i];

      if (inString) {
        if (ch === stringChar && snippet[i - 1] !== '\\') {
          inString = false;
        }
        continue;
      }
      if (ch === '"' || ch === "'" || ch === '`') {
        inString = true;
        stringChar = ch;
        continue;
      }

      if (ch === '{') braces++;
      else if (ch === '}') braces--;
      else if (ch === '(') parens++;
      else if (ch === ')') parens--;
      else if (ch === '[') brackets++;
      else if (ch === ']') brackets--;
    }

    const issues: string[] = [];
    if (braces !== 0) {
      issues.push(`${Math.abs(braces)} unclosed ${braces > 0 ? 'opening' : 'closing'} brace${Math.abs(braces) !== 1 ? 's' : ''}`);
    }
    if (parens !== 0) {
      issues.push(`${Math.abs(parens)} unclosed ${parens > 0 ? 'opening' : 'closing'} paren${Math.abs(parens) !== 1 ? 's' : ''}`);
    }
    if (brackets !== 0) {
      issues.push(`${Math.abs(brackets)} unclosed ${brackets > 0 ? 'opening' : 'closing'} bracket${Math.abs(brackets) !== 1 ? 's' : ''}`);
    }

    return issues.length > 0 ? issues.join('; ') : undefined;
  }

  // Returns a combined semantic trigger string, or undefined if nothing notable.
  getSemanticTrigger(snippet: string | undefined): string | undefined {
    const triggers: string[] = [];
    const thrash = this.getThrashTrigger();
    if (thrash) {
      triggers.push(thrash);
    }
    if (snippet) {
      const syntax = this.getSyntaxTrigger(snippet);
      if (syntax) {
        triggers.push(syntax);
      }
    }
    return triggers.length > 0 ? triggers.join(' | ') : undefined;
  }
}
