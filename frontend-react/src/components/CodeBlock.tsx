import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import css from 'react-syntax-highlighter/dist/esm/languages/prism/css';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('css', css);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('markup', markup);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('typescript', typescript);

const LANGUAGE_ALIASES: Record<string, string> = {
  bash: 'bash',
  css: 'css',
  html: 'markup',
  javascript: 'javascript',
  js: 'javascript',
  json: 'json',
  jsx: 'javascript',
  markdown: 'markup',
  md: 'markup',
  py: 'python',
  python: 'python',
  sh: 'bash',
  shell: 'bash',
  ts: 'typescript',
  tsx: 'typescript',
  typescript: 'typescript',
  xml: 'markup',
};

interface CodeBlockProps {
  language: string;
  code: string;
}

export default function CodeBlock({ language, code }: CodeBlockProps) {
  return (
    <div data-testid="syntax-highlighter">
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={LANGUAGE_ALIASES[language.toLowerCase()] ?? 'markup'}
        PreTag="div"
        customStyle={{
          margin: 0,
          padding: '0.75rem',
          background: 'transparent',
          fontSize: '0.75rem',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
