import { describe, expect, it } from 'vitest';

import { formatReasoning } from './formatReasoning';

describe('formatReasoning', () => {
  it('normalizes repeated reasoning section headings', () => {
    const formatted = formatReasoning(
      '### Relevant Information: Evidence found\n**Gaps or Conflicts:** none\n# Conclusion: approve',
    );

    expect(formatted).toContain('#### **Relevant Information**');
    expect(formatted).toContain('#### **Gaps or Conflicts**');
    expect(formatted).toContain('#### **Conclusion**');
  });

  it('converts bullet glyphs and collapses excess whitespace', () => {
    const formatted = formatReasoning('First point • Second point\n\n\n* Third point');

    expect(formatted).toBe('First point\n- Second point\n- Third point');
  });
});
