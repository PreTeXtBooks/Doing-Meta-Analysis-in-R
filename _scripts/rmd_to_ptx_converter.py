#!/usr/bin/env python3
"""
Convert R Markdown (.Rmd) files to PreTeXt XML format.
Usage: python3 rmd_to_ptx_converter.py <rmd_file> <existing_ptx_file> [output_ptx_file]
If output_ptx_file is omitted, overwrites the existing PTX file.
"""

import re
import sys
import os


# Regex pattern for (ref:label) text references used in fig.cap etc.
_REF_LABEL_PATTERN = re.compile(r'^\(ref:([\w.-]+)\)$')


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def xml_escape_text(text):
    """Escape XML entities in plain text (not math, not code)."""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


def xml_escape_attr(text):
    """Escape XML entities in an attribute value."""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    return text


# ---------------------------------------------------------------------------
# Wrapper info extraction
# ---------------------------------------------------------------------------

def get_wrapper_info(ptx_content):
    """Extract wrapper element info from existing PTX file."""
    m = re.search(r'<(chapter|preface|appendix)(\s[^>]*)?>', ptx_content)
    if not m:
        return None
    tag = m.group(1)
    attrs_str = (m.group(2) or '').strip()
    xml_id_m = re.search(r'xml:id="([^"]*)"', attrs_str)
    xml_id = xml_id_m.group(1) if xml_id_m else ''
    has_xi = 'xmlns:xi' in attrs_str
    title_m = re.search(r'<title>(.*?)</title>', ptx_content, re.DOTALL)
    title = title_m.group(1).strip() if title_m else ''
    return {
        'tag': tag,
        'xml_id': xml_id,
        'title': title,
        'has_xi': has_xi,
    }


# ---------------------------------------------------------------------------
# Rmd front-matter stripping
# ---------------------------------------------------------------------------

def strip_yaml_frontmatter(content):
    """Strip YAML front matter delimited by --- lines."""
    if content.startswith('---'):
        end = content.find('\n---\n', 3)
        if end != -1:
            return content[end + 5:]
        end = content.find('\n---\r\n', 3)
        if end != -1:
            return content[end + 6:]
    return content


def parse_text_references(content):
    """
    Parse (ref:label) text reference definitions from Rmd content.
    These are standalone lines of the form:
        (ref:label) Caption text here.
    Returns a dict mapping label -> text.
    """
    refs = {}
    for m in re.finditer(r'^\(ref:([\w.-]+)\)\s+(.+)$', content, re.MULTILINE):
        refs[m.group(1)] = m.group(2).strip()
    return refs


def preprocess_lines(content):
    """
    Replace standalone \\vspace{...} and <br> lines with blank lines so they
    act as paragraph/list separators rather than stray paragraph content.
    """
    lines = content.split('\n')
    result = []
    for line in lines:
        if re.match(r'^\s*\\vspace\{[^}]*\}\s*$', line):
            result.append('')
        elif re.match(r'^\s*<br\s*/?>\s*$', line, re.IGNORECASE):
            result.append('')
        elif re.match(r'^\s*<br></br>\s*$', line, re.IGNORECASE):
            result.append('')
        else:
            result.append(line)
    return '\n'.join(result)


# ---------------------------------------------------------------------------
# ID generation from heading text
# ---------------------------------------------------------------------------

def make_xml_id(text):
    """Generate a valid xml:id from heading text."""
    # Strip inline markup first
    t = re.sub(r'\*\*([^*]*)\*\*', r'\1', text)
    t = re.sub(r'\*([^*]*)\*', r'\1', t)
    t = re.sub(r'_([^_]*)_', r'\1', t)
    t = re.sub(r'`[^`]*`', '', t)
    t = re.sub(r'\$[^$]*\$', '', t)
    t = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', t)
    t = t.lower()
    t = re.sub(r'[^a-z0-9\s\-]', '', t)
    t = re.sub(r'[\s\-]+', '-', t)
    t = t.strip('-')
    return t or 'sec'


# ---------------------------------------------------------------------------
# Code chunk header parsing
# ---------------------------------------------------------------------------

def parse_chunk_header(header):
    """
    Parse ```{r label, opt=val, ...} or ```{block, type='...'} etc.
    Returns dict with keys: lang, label, opts
    """
    # Strip ``` and braces
    m = re.match(r'^```\{(.+)\}$', header.strip())
    if not m:
        return None
    inner = m.group(1).strip()

    # Split on first comma to get lang+label vs options
    comma_idx = inner.find(',')
    if comma_idx == -1:
        lang_label = inner
        opts_str = ''
    else:
        lang_label = inner[:comma_idx].strip()
        opts_str = inner[comma_idx + 1:]

    # lang_label might be "r" or "r label" or "block"
    parts = lang_label.split(None, 1)
    lang = parts[0].strip() if parts else ''
    label = parts[1].strip() if len(parts) > 1 else None

    # Parse key=value options
    opts = {}
    for om in re.finditer(r'(\w[\w.]*)\s*=\s*(?:\'([^\']*)\'|"([^"]*)"|([^\s,]+))', opts_str):
        key = om.group(1)
        val = om.group(2) if om.group(2) is not None else \
              om.group(3) if om.group(3) is not None else \
              om.group(4)
        opts[key] = val

    # Also check for type in block chunks
    if 'type' not in opts:
        tm = re.search(r"type\s*=\s*['\"]([^'\"]*)['\"]", opts_str)
        if tm:
            opts['type'] = tm.group(1)

    return {'lang': lang, 'label': label, 'opts': opts}


# ---------------------------------------------------------------------------
# Block-level Rmd parser
# ---------------------------------------------------------------------------

def join_para_lines(lines):
    """Join paragraph lines, handling firstcharacter span specially."""
    if not lines:
        return ''
    result = lines[0]
    for line in lines[1:]:
        # If previous ends with firstcharacter span, join without space
        if re.search(r'<span\s+class="firstcharacter">[A-Z]</span>$', result.rstrip()):
            result = result.rstrip() + line.lstrip()
        else:
            result = result + ' ' + line
    return result


def parse_list_items(lines, start, ordered=False):
    """
    Parse an unordered or ordered list. Returns (items, next_i).
    Each item is a string of the item text (possibly multi-line joined).
    """
    items = []
    i = start
    n = len(lines)
    current_lines = []

    def is_item_start(line):
        if ordered:
            return bool(re.match(r'^\s*\d+\.\s', line))
        else:
            return bool(re.match(r'^\s*[*\-]\s', line))

    def strip_bullet(line):
        if ordered:
            return re.sub(r'^\s*\d+\.\s*', '', line)
        else:
            return re.sub(r'^\s*[*\-]\s*', '', line)

    while i < n:
        line = lines[i]
        if is_item_start(line):
            if current_lines:
                items.append(' '.join(l.strip() for l in current_lines if l.strip()))
            current_lines = [strip_bullet(line)]
            i += 1
        elif (line.startswith('  ') or line.startswith('\t')) and current_lines:
            # Continuation of current item
            current_lines.append(line.strip())
            i += 1
        elif not line.strip() and current_lines:
            # Blank line - check if list continues
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and (is_item_start(lines[j]) or
                          (lines[j].startswith('  ') and current_lines)):
                current_lines.append('')
                i = j
            else:
                break
        else:
            break

    if current_lines:
        text = ' '.join(l.strip() for l in current_lines if l.strip())
        if text:
            items.append(text)
    return items, i


def parse_rmd_blocks(content, text_refs=None):
    """
    Parse Rmd content into a flat list of block dicts.
    Block types: heading, para, code, block_chunk, hr, bq, ul, ol, dm, img
    """
    content = strip_yaml_frontmatter(content)
    text_refs = parse_text_references(content)
    content = preprocess_lines(content)
    lines = content.split('\n')
    blocks = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Code block: ```{r ...} or ```{block ...} etc.
        if re.match(r'^```\{', line.strip()):
            header = line.strip()
            j = i + 1
            # Find closing ```
            while j < n:
                stripped = lines[j].strip()
                if stripped == '```':
                    break
                # block2 type can close with ``` inside the content area
                j += 1
            code_lines = lines[i + 1:j]
            code = '\n'.join(code_lines)
            chunk_info = parse_chunk_header(header)
            if chunk_info and chunk_info['lang'] in ('block', 'block2'):
                blocks.append({
                    'type': 'block_chunk',
                    'btype': chunk_info['opts'].get('type', 'box'),
                    'content': code,
                })
            else:
                blocks.append({
                    'type': 'code',
                    'header': header,
                    'code': code,
                    'info': chunk_info,
                    'text_refs': text_refs,
                })
            i = j + 1
            continue

        # Fenced code block without options (```lang or ``` plain)
        if re.match(r'^```', line.strip()) and not re.match(r'^```\{', line.strip()):
            j = i + 1
            while j < n and lines[j].strip() != '```':
                j += 1
            code = '\n'.join(lines[i + 1:j])
            lang_m = re.match(r'^```(\w*)', line.strip())
            lang = lang_m.group(1) if lang_m else ''
            blocks.append({'type': 'raw_code', 'lang': lang or 'r', 'code': code})
            i = j + 1
            continue

        # Heading
        hm = re.match(r'^(#{1,4})\s+(.*)', line)
        if hm:
            level = len(hm.group(1))
            heading_text = hm.group(2).strip()
            # Extract {#id} or {-} labels
            label_m = re.search(r'\{([^}]*)\}$', heading_text)
            heading_id = None
            if label_m:
                label_content = label_m.group(1)
                heading_text = heading_text[:label_m.start()].strip()
                id_m = re.search(r'#([\w\-]+)', label_content)
                if id_m:
                    heading_id = id_m.group(1)
            if heading_id is None:
                heading_id = make_xml_id(heading_text)
            blocks.append({
                'type': 'heading',
                'level': level,
                'text': heading_text,
                'id': heading_id,
            })
            i += 1
            continue

        # Horizontal rule
        if line.strip() in ('---', '===', '***') and len(line.strip()) >= 3 and \
                len(set(line.strip())) == 1:
            blocks.append({'type': 'hr'})
            i += 1
            continue

        # Display math $$...$$ (may be multi-line)
        if line.strip().startswith('$$'):
            stripped = line.strip()
            # Single-line $$...$$
            if stripped.startswith('$$') and stripped.endswith('$$') and len(stripped) > 4:
                math = stripped[2:-2].strip()
                # Drop chapter-end marker
                if r'\blacksquare' not in math and r'\tag' not in math:
                    blocks.append({'type': 'dm', 'content': math})
                i += 1
                continue
            # Multi-line $$\n...\n$$
            elif stripped == '$$':
                j = i + 1
                while j < n and lines[j].strip() != '$$':
                    j += 1
                math = '\n'.join(lines[i + 1:j]).strip()
                if r'\blacksquare' not in math and r'\tag' not in math:
                    blocks.append({'type': 'dm', 'content': math})
                i = j + 1
                continue

        # Standalone img tag
        img_m = re.match(r'^\s*<img\s[^>]*src="([^"]*)"[^>]*/>\s*$', line, re.IGNORECASE)
        if img_m:
            blocks.append({'type': 'img', 'src': img_m.group(1)})
            i += 1
            continue

        # Blockquote
        if line.startswith('>'):
            bq_lines = []
            while i < n:
                l = lines[i]
                if l.startswith('>'):
                    bq_lines.append(l[1:].lstrip())
                    i += 1
                elif not l.strip():
                    # Check if quote continues after blank
                    j = i + 1
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and lines[j].startswith('>'):
                        bq_lines.append('')
                        i = j
                    else:
                        break
                else:
                    break
            blocks.append({'type': 'bq', 'lines': bq_lines})
            continue

        # Unordered list
        if re.match(r'^\s*[*\-]\s', line) and not line.strip().startswith('```'):
            items, next_i = parse_list_items(lines, i, ordered=False)
            if items:
                blocks.append({'type': 'ul', 'items': items})
            i = next_i
            continue

        # Ordered list
        if re.match(r'^\s*\d+\.\s', line):
            items, next_i = parse_list_items(lines, i, ordered=True)
            if items:
                blocks.append({'type': 'ol', 'items': items})
            i = next_i
            continue

        # Text reference definitions: (ref:label) text... — skip these lines
        if re.match(r'^\(ref:[\w.-]+\)\s', line):
            i += 1
            continue

        # Regular paragraph - collect until blank line or structural element
        para_lines = []
        while i < n:
            l = lines[i]
            if not l.strip():
                break
            if re.match(r'^#{1,4}\s', l):
                break
            if re.match(r'^```', l.strip()):
                break
            if re.match(r'^\s*[*\-]\s', l) and not para_lines:
                break
            if re.match(r'^\s*\d+\.\s', l) and not para_lines:
                break
            if l.startswith('>') and not para_lines:
                break
            if l.strip() in ('---', '===') and len(set(l.strip())) == 1:
                # Don't absorb HR into paragraph
                break
            para_lines.append(l)
            i += 1

        if para_lines:
            text = join_para_lines(para_lines)
            # Skip if it's only whitespace/vspace/br
            stripped = re.sub(r'\\vspace\{[^}]*\}', '', text).strip()
            stripped = re.sub(r'<br\s*/?>', '', stripped, flags=re.IGNORECASE).strip()
            stripped = re.sub(r'<br></br>', '', stripped, flags=re.IGNORECASE).strip()
            if stripped:
                blocks.append({'type': 'para', 'text': text})

    return blocks


# ---------------------------------------------------------------------------
# Inline converter
# ---------------------------------------------------------------------------

def convert_inline(text):
    """
    Convert inline Rmd markdown to PreTeXt XML.
    Returns a string of PreTeXt-valid XML content.
    """
    parts = []
    pos = 0
    length = len(text)

    while pos < length:
        # ---- Display math $$...$$ (inline occurrence, e.g. at end of para) ----
        if text[pos:pos+2] == '$$':
            end = text.find('$$', pos + 2)
            if end != -1:
                math = text[pos + 2:end]
                # Escape XML chars in math (& and < are invalid XML raw)
                math = math.replace('&', '&amp;').replace('<', '&lt;')
                parts.append(('me', math))
                pos = end + 2
                continue

        # ---- Inline math $...$ ----
        if text[pos] == '$' and (pos == 0 or text[pos-1] != '\\'):
            # Find closing $, not $$
            j = pos + 1
            while j < length:
                if text[j] == '$' and text[j-1] != '\\':
                    break
                j += 1
            if j < length and text[j] == '$':
                math = text[pos + 1:j]
                # Escape XML chars in math
                math = math.replace('&', '&amp;').replace('<', '&lt;')
                parts.append(('m', math))
                pos = j + 1
                continue

        # ---- Inline code `...` ----
        if text[pos] == '`':
            j = pos + 1
            while j < length and text[j] != '`':
                j += 1
            if j < length:
                code = text[pos + 1:j]
                parts.append(('c', xml_escape_text(code)))
                pos = j + 1
                continue

        # ---- Footnote ^[...] ----
        if text[pos:pos+2] == '^[':
            # Find matching ]
            depth = 1
            j = pos + 2
            while j < length and depth > 0:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                j += 1
            if depth == 0:
                fn_content = text[pos + 2:j - 1]
                parts.append(('fn', convert_inline(fn_content)))
                pos = j
                continue

        # ---- Markdown image ![alt](src) ----
        if text[pos] == '!' and pos + 1 < length and text[pos + 1] == '[':
            m = re.match(r'!\[([^\]]*)\]\(([^)]*)\)', text[pos:])
            if m:
                src = m.group(2).strip()
                # Drop badges / remote URLs; render local paths as <image>
                if src.startswith('http://') or src.startswith('https://'):
                    pos += m.end()
                else:
                    parts.append(('raw', f'<image source="{xml_escape_attr(src)}"/>'))
                    pos += m.end()
                continue

        # ---- Link [text](url) ----
        if text[pos] == '[':
            # Find matching ]
            depth = 1
            j = pos + 1
            while j < length and depth > 0:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                j += 1
            if depth == 0 and j < length and text[j] == '(':
                # Find closing )
                k = j + 1
                paren_depth = 1
                while k < length and paren_depth > 0:
                    if text[k] == '(':
                        paren_depth += 1
                    elif text[k] == ')':
                        paren_depth -= 1
                    k += 1
                if paren_depth == 0:
                    link_text = text[pos + 1:j - 1]
                    url = text[j + 1:k - 1]
                    converted_text = convert_inline(link_text)
                    url_escaped = xml_escape_attr(url)
                    if not converted_text.strip():
                        # Empty link text (e.g. badge image was dropped) — drop the link
                        pos = k
                    elif converted_text.strip() == url.strip():
                        parts.append(('raw', f'<url href="{url_escaped}"/>'))
                        pos = k
                    else:
                        parts.append(('raw', f'<url href="{url_escaped}">{converted_text}</url>'))
                        pos = k
                    continue

        # ---- Cross-reference \@ref(label) ----
        if text[pos:pos+5] == '\\@ref':
            m = re.match(r'\\@ref\(([^)]+)\)', text[pos:])
            if m:
                ref = m.group(1)
                parts.append(('raw', f'<xref ref="{ref}"/>'))
                pos += m.end()
                continue

        # ---- Index \index{...} ----
        if text[pos:pos+7] == '\\index{':
            # Find matching }
            depth = 1
            j = pos + 7
            while j < length and depth > 0:
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                j += 1
            term = text[pos + 7:j - 1]
            parts.append(('idx', xml_escape_text(term)))
            pos = j
            continue

        # ---- Citation [@key] or [-@key] ----
        if text[pos] == '[':
            m = re.match(r'\[[-]?@[^\]]+\]', text[pos:])
            if m:
                # Drop citation
                pos += m.end()
                continue

        # ---- \vspace{...} → drop ----
        if text[pos:pos+8] == '\\vspace{':
            m = re.match(r'\\vspace\{[^}]*\}', text[pos:])
            if m:
                pos += m.end()
                continue

        # ---- <br></br> or <br/> → drop ----
        if text[pos] == '<':
            m = re.match(r'<br\s*/?>', text[pos:], re.IGNORECASE)
            if m:
                pos += m.end()
                continue
            m = re.match(r'<br></br>', text[pos:], re.IGNORECASE)
            if m:
                pos += m.end()
                continue
            # firstcharacter span → keep just the letter
            m = re.match(r'<span\s+class="firstcharacter">([^<]*)</span>', text[pos:], re.IGNORECASE)
            if m:
                parts.append(('text', xml_escape_text(m.group(1))))
                pos += m.end()
                continue
            # img tag inline → figure
            m = re.match(r'<img\s[^>]*src="([^"]*)"[^>]*/>', text[pos:], re.IGNORECASE)
            if m:
                src = m.group(1)
                parts.append(('raw', f'<image source="{xml_escape_attr(src)}"/>'))
                pos += m.end()
                continue
            # Other HTML tags - strip them
            m = re.match(r'<[^>]+>', text[pos:])
            if m:
                pos += m.end()
                continue

        # ---- Bold **...** ----
        if text[pos:pos+2] == '**':
            j = text.find('**', pos + 2)
            if j != -1:
                inner = text[pos + 2:j]
                parts.append(('alert', convert_inline(inner)))
                pos = j + 2
                continue

        # ---- Italic _..._ ----
        if text[pos] == '_':
            # Find closing _ (not preceded by _)
            j = pos + 1
            while j < length:
                if text[j] == '_' and (j + 1 >= length or text[j + 1] != '_'):
                    break
                j += 1
            if j < length and j > pos + 1:
                inner = text[pos + 1:j]
                parts.append(('em', convert_inline(inner)))
                pos = j + 1
                continue

        # ---- Italic *...* (single asterisk) ----
        if text[pos] == '*' and (pos == 0 or text[pos - 1] != '*'):
            j = pos + 1
            while j < length:
                if text[j] == '*' and (j + 1 >= length or text[j + 1] != '*'):
                    break
                j += 1
            if j < length and j > pos + 1:
                inner = text[pos + 1:j]
                parts.append(('em', convert_inline(inner)))
                pos = j + 1
                continue

        # ---- Backslash escapes ----
        if text[pos] == '\\' and pos + 1 < length:
            next_char = text[pos + 1]
            if next_char in ('*', '_', '`', '[', ']', '(', ')', '\\', '#', '!', '&'):
                parts.append(('text', xml_escape_text(next_char)))
                pos += 2
                continue
            # Other backslash sequences: just skip the backslash
            # (like \n, \, etc.)

        # ---- Plain text character ----
        # Collect a run of plain characters
        end = pos + 1
        while end < length:
            c = text[end]
            if c in ('$', '`', '^', '[', '\\', '<', '>'):
                break
            if c == '*':
                break
            if c == '_':
                break
            end += 1
        chunk = text[pos:end]
        parts.append(('text', xml_escape_text(chunk)))
        pos = end

    # Build output
    out = []
    for kind, content in parts:
        if kind == 'text':
            out.append(content)
        elif kind == 'raw':
            out.append(content)
        elif kind == 'm':
            out.append(f'<m>{content}</m>')
        elif kind == 'me':
            out.append(f'<me>{content}</me>')
        elif kind == 'c':
            out.append(f'<c>{content}</c>')
        elif kind == 'fn':
            out.append(f'<fn>{content}</fn>')
        elif kind == 'alert':
            out.append(f'<alert>{content}</alert>')
        elif kind == 'em':
            out.append(f'<em>{content}</em>')
        elif kind == 'idx':
            out.append(f'<idx><h>{content}</h></idx>')

    return ''.join(out)


# ---------------------------------------------------------------------------
# PTX output builder
# ---------------------------------------------------------------------------

class PTXWriter:
    def __init__(self):
        self.lines = []
        self._indent = 0

    def indent(self, n=1):
        self._indent += n

    def dedent(self, n=1):
        self._indent -= n

    def write(self, line=''):
        if line:
            self.lines.append('  ' * self._indent + line)
        else:
            self.lines.append('')

    def open_tag(self, tag, attrs=''):
        if attrs:
            self.write(f'<{tag} {attrs}>')
        else:
            self.write(f'<{tag}>')
        self._indent += 1

    def close_tag(self, tag):
        self._indent -= 1
        self.write(f'</{tag}>')

    def self_close(self, tag, attrs=''):
        if attrs:
            self.write(f'<{tag} {attrs}/>')
        else:
            self.write(f'<{tag}/>')

    def write_inline_tag(self, tag, content, attrs=''):
        """Write <tag>content</tag> on a single line."""
        if attrs:
            self.write(f'<{tag} {attrs}>{content}</{tag}>')
        else:
            self.write(f'<{tag}>{content}</{tag}>')

    def write_verbatim_block(self, open_line, close_line, content_lines):
        """Write an open tag, then content lines verbatim (no extra indent), then close tag.
        Lines are XML-escaped so that characters like < and & are valid in XML text."""
        prefix = '  ' * self._indent
        self.lines.append(prefix + open_line)
        for line in content_lines:
            self.lines.append(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        self.lines.append(prefix + close_line)

    def get_output(self):
        return '\n'.join(self.lines)


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------

def render_para_text(text, writer):
    """Render a paragraph's inline text, possibly as multiple <p> elements
    if the text contains figure-like img tags."""
    # Check if paragraph is just \vspace or br → skip
    stripped = re.sub(r'\\vspace\{[^}]*\}', '', text).strip()
    stripped = re.sub(r'<br\s*/?>', '', stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r'<br></br>', '', stripped, flags=re.IGNORECASE).strip()
    if not stripped:
        return

    # Check if paragraph is purely an img tag → render as figure
    img_only = re.match(
        r'^\s*(?:\\vspace\{[^}]*\}\s*|<br\s*/?>\s*|<br></br>\s*)*'
        r'<img\s[^>]*src="([^"]*)"[^>]*/>'
        r'\s*(?:\\vspace\{[^}]*\}\s*|<br\s*/?>\s*|<br></br>\s*)*$',
        text, re.IGNORECASE
    )
    if img_only:
        src = img_only.group(1)
        writer.open_tag('figure')
        writer.self_close('image', f'source="{xml_escape_attr(src)}"')
        writer.close_tag('figure')
        return

    converted = convert_inline(text)
    if not converted.strip():
        return

    writer.open_tag('p')
    # Write each line of the converted text
    for line in converted.split('\n'):
        writer.write(line)
    writer.close_tag('p')


def render_blockquote(bq_lines, writer):
    """Render a blockquote block."""
    # Collect non-empty text
    full = ' '.join(l for l in bq_lines if l.strip())
    if not full.strip():
        return
    writer.open_tag('blockquote')
    writer.open_tag('p')
    writer.write(convert_inline(full))
    writer.close_tag('p')
    writer.close_tag('blockquote')


def render_list(items, ordered, writer):
    """Render a list block."""
    tag = 'ol' if ordered else 'ul'
    writer.open_tag(tag)
    for item in items:
        if not item.strip():
            continue
        writer.open_tag('li')
        writer.open_tag('p')
        writer.write(convert_inline(item))
        writer.close_tag('p')
        writer.close_tag('li')
    writer.close_tag(tag)


def render_code(block, writer):
    """Render an R code chunk."""
    info = block.get('info') or {}
    opts = info.get('opts', {}) if info else {}
    label = info.get('label') if info else None
    lang = (info.get('lang', 'r') if info else 'r') or 'r'
    code = block.get('code', '')
    text_refs = block.get('text_refs') or {}

    echo_opt = opts.get('echo', 'T')

    # For echo=F chunks, check if the code is purely knitr::include_graphics()
    if echo_opt in ('FALSE', 'F', 'false'):
        imgs = re.findall(r"knitr::include_graphics\(['\"]([^'\"]+)['\"]\)", code)
        if imgs:
            # Resolve caption: fig.cap may be a (ref:xxx) reference
            cap_raw = opts.get('fig.cap', '') or opts.get('fig_cap', '')
            if cap_raw:
                ref_m = _REF_LABEL_PATTERN.match(cap_raw.strip())
                if ref_m:
                    cap_raw = text_refs.get(ref_m.group(1), cap_raw)
                caption = convert_inline(cap_raw)
            else:
                caption = ''

            # Build figure element
            if label:
                fig_attrs = f'xml:id="fig:{label}"'
            else:
                fig_attrs = ''

            writer.open_tag('figure', fig_attrs)

            if caption:
                writer.write_inline_tag('caption', caption)

            for img_path in imgs:
                # Map images/xxx.png -> generated/xxx.png
                src = img_path.replace('images/', 'generated/', 1) if img_path.startswith('images/') else img_path
                writer.self_close('image', f'source="{xml_escape_attr(src)}"')

            writer.close_tag('figure')
        # Skip all other echo=F chunks (pure R-generated plots, setup, etc.)
        return

    if not code.strip():
        return

    if label:
        tag_attrs = f'xml:id="{label}" language="{lang}"'
    else:
        tag_attrs = f'language="{lang}"'

    writer.open_tag('program', tag_attrs)
    code_lines = code.rstrip('\n').split('\n')
    writer.write_verbatim_block('<input>', '</input>', code_lines)
    writer.close_tag('program')


def render_raw_code(block, writer):
    """Render a raw fenced code block."""
    lang = block.get('lang', 'r')
    code = block.get('code', '')
    if not code.strip():
        return
    writer.open_tag('program', f'language="{lang}"')
    code_lines = code.rstrip('\n').split('\n')
    writer.write_verbatim_block('<input>', '</input>', code_lines)
    writer.close_tag('program')


def render_block_chunk(block, writer):
    """Render a {block} chunk as a <note>."""
    content = block.get('content', '')
    btype = block.get('btype', 'box')

    if btype == 'boxquestion':
        tag = 'exercise'
    else:
        tag = 'note'

    writer.open_tag(tag)
    # Parse the block content as its own mini-document
    sub_blocks = parse_rmd_blocks(content + '\n')
    render_content_blocks(sub_blocks, writer)
    writer.close_tag(tag)


def render_display_math(block, writer):
    """Render a display math block."""
    content = block.get('content', '')
    writer.write_inline_tag('me', content)


def render_img(block, writer):
    """Render a standalone img block as a figure."""
    src = block.get('src', '')
    writer.open_tag('figure')
    writer.self_close('image', f'source="{xml_escape_attr(src)}"')
    writer.close_tag('figure')


def render_content_blocks(blocks, writer):
    """Render a sequence of non-heading blocks to PTX."""
    for block in blocks:
        btype = block['type']
        if btype == 'hr':
            pass  # Drop horizontal rules
        elif btype == 'para':
            render_para_text(block['text'], writer)
        elif btype == 'code':
            render_code(block, writer)
        elif btype == 'raw_code':
            render_raw_code(block, writer)
        elif btype == 'block_chunk':
            render_block_chunk(block, writer)
        elif btype == 'bq':
            render_blockquote(block['lines'], writer)
        elif btype == 'ul':
            render_list(block['items'], ordered=False, writer=writer)
        elif btype == 'ol':
            render_list(block['items'], ordered=True, writer=writer)
        elif btype == 'dm':
            render_display_math(block, writer)
        elif btype == 'img':
            render_img(block, writer)
        elif btype == 'heading':
            # Headings inside block chunks (sub-headings) rendered as paragraphs
            lvl = block['level']
            if lvl >= 5:
                writer.open_tag('p')
                writer.write(f'<alert>{convert_inline(block["text"])}</alert>')
                writer.close_tag('p')


# ---------------------------------------------------------------------------
# Main PTX structure builder
# ---------------------------------------------------------------------------

SECTION_TAGS = {
    2: 'section',
    3: 'subsection',
    4: 'subsubsection',
    5: 'paragraphs',
}


def build_ptx(blocks, wrapper_info):
    """
    Build the complete PTX document from parsed blocks and wrapper info.
    Returns a string of PTX XML.
    """
    writer = PTXWriter()

    # XML declaration
    writer.write('<?xml version="1.0" encoding="UTF-8"?>')

    # Wrapper opening tag
    tag = wrapper_info['tag']
    xml_id = wrapper_info['xml_id']
    title = wrapper_info['title']

    writer.open_tag(tag, f'xml:id="{xml_id}"' +
                    (' xmlns:xi="http://www.w3.org/2001/XInclude"' if wrapper_info.get('has_xi') else ''))
    writer.write_inline_tag('title', title)
    writer.write()

    # Split blocks into: pre-first-section and sectioned
    # Find first level-2 heading
    first_section_idx = None
    for idx, b in enumerate(blocks):
        if b['type'] == 'heading' and b['level'] == 2:
            first_section_idx = idx
            break

    # Check if there are any sections at all
    has_sections = first_section_idx is not None

    # Pre-section content (skip the top-level # heading)
    pre_blocks = []
    main_start = 0
    for idx, b in enumerate(blocks):
        if b['type'] == 'heading' and b['level'] == 1:
            main_start = idx + 1
            break

    if has_sections:
        pre_blocks = [b for b in blocks[main_start:first_section_idx]
                      if b['type'] not in ('heading',)]
        # Filter out pure HR/whitespace blocks
        pre_blocks = [b for b in pre_blocks if b['type'] != 'hr']
    else:
        pre_blocks = [b for b in blocks[main_start:]
                      if b['type'] not in ('heading',) and b['type'] != 'hr']

    # Render introduction (pre-section content)
    if has_sections and pre_blocks:
        writer.open_tag('introduction')
        render_content_blocks(pre_blocks, writer)
        writer.close_tag('introduction')
        writer.write()
    elif not has_sections:
        render_content_blocks(pre_blocks, writer)

    if has_sections:
        # Process sections with a stack
        # Stack entries: (level, tag)
        section_stack = []

        def close_down_to(target_level):
            """Close all open sections at level >= target_level."""
            while section_stack and section_stack[-1][0] >= target_level:
                lvl, stag = section_stack.pop()
                writer.close_tag(stag)
                writer.write()

        for b in blocks[main_start:]:
            if b['type'] == 'heading' and b['level'] >= 2:
                level = b['level']
                stag = SECTION_TAGS.get(level, 'section')

                # Close sections at same or higher level
                close_down_to(level)

                # Open new section
                sec_id = b['id']
                writer.open_tag(stag, f'xml:id="{sec_id}"')
                writer.write_inline_tag('title', convert_inline(b['text']))
                writer.write()
                section_stack.append((level, stag))

            elif b['type'] == 'heading' and b['level'] == 1:
                # Additional level-1 headings (shouldn't happen but handle gracefully)
                pass
            else:
                # Content block
                if section_stack:
                    render_content_blocks([b], writer)
                # else: content outside sections after first section was opened - skip

        # Close all remaining open sections
        while section_stack:
            lvl, stag = section_stack.pop()
            writer.close_tag(stag)
            writer.write()

    # Close wrapper
    writer.close_tag(tag)

    return writer.get_output()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def convert_file(rmd_path, ptx_path, output_path=None):
    """Convert an Rmd file to PTX, using wrapper info from existing PTX."""
    with open(rmd_path, 'r', encoding='utf-8') as f:
        rmd_content = f.read()

    with open(ptx_path, 'r', encoding='utf-8') as f:
        ptx_content = f.read()

    wrapper_info = get_wrapper_info(ptx_content)
    if not wrapper_info:
        raise ValueError(f"Could not find wrapper element in {ptx_path}")

    text_refs = parse_text_references(rmd_content)
    blocks = parse_rmd_blocks(rmd_content, text_refs=text_refs)
    ptx_output = build_ptx(blocks, wrapper_info)

    out_path = output_path or ptx_path
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(ptx_output)
        f.write('\n')

    return out_path


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <rmd_file> <existing_ptx_file> [output_ptx_file]")
        sys.exit(1)

    rmd_file = sys.argv[1]
    ptx_file = sys.argv[2]
    out_file = sys.argv[3] if len(sys.argv) > 3 else None

    result = convert_file(rmd_file, ptx_file, out_file)
    print(f"Written: {result}")
