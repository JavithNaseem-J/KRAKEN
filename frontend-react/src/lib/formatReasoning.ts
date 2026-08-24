export function formatReasoning(text: string): string {
  if (!text) return '';
  return text
    .replace(
      /(?:###|\*\*|#)*\s*(RELEVANT INFORMATION|GAPS OR CONFLICTS|CONCLUSION):?\s*(?:\*\*|#)*/gi,
      '\n\n#### **$1**\n\n',
    )
    .replace(/(?:^|\n)\s*[•\*]\s*/g, '\n- ')
    .replace(/([^\n])\s*•\s*/g, '$1\n- ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
