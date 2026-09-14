"""Build a self-contained offline reading edition using the Python standard library."""
from pathlib import Path
from html import escape
import hashlib
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'IDL-生产技术规范.md'
OUTPUT = ROOT / 'docs' / 'IDL-生产技术规范.html'


def inline(value):
    parts = re.split(r'(`[^`]+`)', value)
    output = []
    for part in parts:
        if part.startswith('`') and part.endswith('`'):
            output.append('<code>' + escape(part[1:-1]) + '</code>')
            continue
        part = escape(part)
        part = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', part)
        part = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', part)
        output.append(part)
    return ''.join(output)


def render(markdown):
    lines = markdown.splitlines()
    output, toc = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.startswith('<!--'):
            i += 1
            continue
        if line.startswith('```'):
            lang = line[3:].strip()
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i])
                i += 1
            output.append('<pre aria-label="' + escape(lang or '示例') + '"><code>' + escape('\n'.join(code)) + '</code></pre>')
            i += 1
            continue
        heading = re.match(r'^(#{1,4})\s+(.+)$', line)
        if heading:
            level, title = len(heading[1]), heading[2]
            anchor = f'section-{len(toc)+1}' if level == 2 else f'heading-{i}'
            if level == 2:
                toc.append((anchor, title))
            output.append(f'<h{level} id="{anchor}">{inline(title)}</h{level}>')
            i += 1
            continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                    rows.append(cells)
                i += 1
            table = '<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">'+inline(c)+'</th>' for c in rows[0]) + '</tr></thead><tbody>'
            for row in rows[1:]:
                table += '<tr>' + ''.join('<td>'+inline(c)+'</td>' for c in row) + '</tr>'
            output.append(table + '</tbody></table></div>')
            continue
        if re.match(r'^(?:- |\d+\. )', line):
            ordered = bool(re.match(r'^\d+\. ', line))
            tag = 'ol' if ordered else 'ul'
            items = []
            pattern = r'^\d+\. ' if ordered else r'^- '
            while i < len(lines) and re.match(pattern, lines[i]):
                items.append('<li>' + inline(re.sub(pattern, '', lines[i])) + '</li>')
                i += 1
            output.append(f'<{tag}>' + ''.join(items) + f'</{tag}>')
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|<!--|- |\d+\. )', lines[i]):
            paragraph.append(lines[i])
            i += 1
        output.append('<p>' + inline(' '.join(paragraph)) + '</p>')
    return '\n'.join(output), toc


def main():
    markdown = SOURCE.read_text(encoding='utf-8')
    if '<!-- OPERATIONS_SECTIONS -->' in markdown or '<!-- DELIVERY_APPENDIX -->' in markdown:
        raise SystemExit('Document contains unassembled sections')
    content, toc = render(markdown)
    contract_bytes = (ROOT / 'contracts/openapi.yaml').read_bytes()
    contract = contract_bytes.decode('utf-8').replace('\r\n', '\n')
    digest = hashlib.sha256(contract_bytes).hexdigest()
    links = ''.join(f'<a href="#{anchor}">{escape(title)}</a>' for anchor, title in toc)
    css = '''
    :root{color-scheme:light;--ink:#18202b;--muted:#5c6674;--line:#d8dfe6;--blue:#1c4b73}
    *{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}
    body{margin:0;background:#f5f6f8;color:var(--ink);font:16px/1.85 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
    .layout{display:grid;grid-template-columns:264px minmax(0,1000px);max-width:1320px;margin:auto}
    nav{position:sticky;top:0;align-self:start;height:100vh;overflow:auto;padding:30px 24px;font-size:13px}
    nav .brand{font-size:17px;font-weight:700;color:var(--ink);margin-bottom:16px}
    nav a{display:block;padding:5px 0;text-decoration:none;color:var(--muted);line-height:1.55}
    nav a:hover{color:var(--blue)}main{min-width:0;background:white;padding:58px 62px 80px;box-shadow:0 0 0 1px #e5e8ec}
    h1,h2,h3{color:#000;line-height:1.4;letter-spacing:0}h1{font-size:34px;margin:0 0 16px}
    h2{font-size:24px;margin:48px 0 18px}h3{font-size:19px;margin:32px 0 12px}
    p{margin:16px 0}a{color:var(--blue);text-underline-offset:3px;overflow-wrap:anywhere}
    code{font:0.9em/1.55 Consolas,"Microsoft YaHei",monospace;overflow-wrap:anywhere}
    p code,td code,li code{background:#f1f3f6;padding:2px 4px;border-radius:3px}
    pre{padding:20px 22px;background:#f2f4f6;border:1px solid var(--line);border-radius:5px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;font-size:14px}
    .table-wrap{overflow-x:auto;margin:22px 0 26px}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.7;table-layout:fixed}
    th,td{border:1px solid var(--line);padding:12px 14px;vertical-align:middle;overflow-wrap:anywhere}
    th{background:#e8eef4;color:#000;text-align:left;font-weight:650}tbody tr:nth-child(even){background:#fafbfc}
    ul,ol{padding-left:1.6em}li{margin:9px 0}details{margin:24px 0}summary{cursor:pointer;font-weight:650}
    .meta{font-size:13px;color:var(--muted)}.toolbar{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-bottom:34px}
    .toolbar a{padding:6px 10px;border:1px solid var(--line);border-radius:4px;text-decoration:none}
    @media(max-width:980px){.layout{display:block}nav{position:static;height:auto;max-height:290px;border-bottom:1px solid var(--line);padding:22px}main{padding:32px 22px}h1{font-size:28px}h2{font-size:22px}th,td{padding:9px}table{font-size:13px}}
    @media print{@page{size:A4;margin:18mm}body{background:#fff;font-size:10.5pt;line-height:1.65}.layout{display:block;max-width:none}nav,.toolbar{display:none}main{box-shadow:none;padding:0}h1{font-size:24pt}h2{font-size:17pt;break-after:avoid}h3{break-after:avoid}p{orphans:3;widows:3}thead{display:table-header-group}tr{break-inside:avoid}pre,td,th{font-size:9pt}pre{white-space:pre-wrap}a{color:inherit}details:not([open]){display:none}}
    '''
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IDL生产技术规范</title><style>{css}</style></head><body><div class="layout"><nav aria-label="文档目录"><div class="brand">IDL生产技术规范</div><p class="meta">OpenAPI 3.1.0<br>版本 1.0.0 · 2026年9月14日</p>{links}<a href="#contract-source">完整契约源文件</a></nav><main><div class="toolbar"><a href="IDL-生产技术规范.md" download>Markdown 源文档</a><a href="../contracts/openapi.yaml" download>OpenAPI 契约</a><a href="../README.md">工程使用说明</a></div>{content}<h2 id="contract-source">完整契约源文件</h2><p>以下为本阅读版生成时的完整契约快照。维护时修改仓库中的 contracts/openapi.yaml 后重新构建阅读版。</p><p class="meta">契约 SHA256 <code>{digest}</code></p><details><summary>展开 OpenAPI YAML</summary><pre><code>{escape(contract)}</code></pre></details></main></div></body></html>'''
    OUTPUT.write_text(html, encoding='utf-8')
    print(f'Built HTML reading edition: {len(toc)} sections, {len(html)} characters')


if __name__ == '__main__':
    main()
