"""Serialized, atomic updates to the account workbook; credentials stay local."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import io
import re
import threading
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import quoteattr

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('', NS)
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
KNOWN_NAMESPACES = {'mc': MC, 'x14ac': 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac'}
def tag(name):
    return '{' + NS + '}' + name


@dataclass(frozen=True)
class ExcelAccount:
    row: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    day: int | None = None


class AccountWorkbook:
    def __init__(self, path, *, status_marks=('X', 'V')):
        self.path = Path(path)
        self.status_marks = status_marks
        self.lock = threading.RLock()
        self.seen = set()
        self.owners = {}
        with self.lock:
            self._read()
            headers = [self._value(f'{chr(65+i)}1') for i in range(20)]
            if headers[:4] != ['STT', 'TK', 'MK', 'Status'] or headers[4:19] != [str(i) for i in range(1,16)] or headers[19].casefold() != 'hoàn thành':
                raise ValueError('Excel cần cột STT, TK, MK, Status, 1–15, Hoàn Thành.')
            if not self.rows:
                raise ValueError('Excel chưa có hàng tài khoản/mật khẩu hợp lệ.')
            self._totals()
            # Detect a locked/unwritable workbook before sending any game input.
            self._save()

    def _read(self):
        with zipfile.ZipFile(self.path) as archive:
            self.parts = {i.filename: (i, archive.read(i.filename)) for i in archive.infolist()}
        workbook = ET.fromstring(self.parts['xl/workbook.xml'][1])
        relation = ET.fromstring(self.parts['xl/_rels/workbook.xml.rels'][1])
        first = workbook.find(tag('sheets'))[0]
        rid = first.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        target = next(x.attrib['Target'] for x in relation if x.attrib['Id'] == rid)
        self.sheet_path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        sheet_xml = self.parts[self.sheet_path][1]
        self.namespaces = dict(pair for _, pair in ET.iterparse(io.BytesIO(sheet_xml), events=['start-ns']))
        self.sheet = ET.fromstring(sheet_xml)
        self.data = self.sheet.find(tag('sheetData'))
        self.sheet_rows = {int(r.attrib['r']): r for r in self.data}
        self.cells = {c.attrib['r']: c for row in self.data for c in row}
        strings = self.parts.get('xl/sharedStrings.xml')
        self.strings = [''.join(x.itertext()) for x in ET.fromstring(strings[1])] if strings else []
        # Re-discover the list on each read instead of retaining the old length.
        self.rows = [r for r in sorted(self.sheet_rows) if r > 1
                     and self._value(f'A{r}').strip() != 'Tổng đã hoàn thành'
                     and self._value(f'B{r}') and self._value(f'C{r}')
                     and self.cells[f'B{r}'].find(tag('f')) is None]

    def _cell(self, address):
        if address not in self.cells:
            rownum = int(re.search(r'\d+', address)[0])
            row = self.sheet_rows.get(rownum)
            if row is None:
                row = ET.SubElement(self.data, tag('row'), r=str(rownum))
                self.sheet_rows[rownum] = row
            cell = ET.Element(tag('c'), r=address)
            col = re.match(r'[A-Z]+', address)[0]
            def index(s):
                n = 0
                for char in s:
                    n = n * 26 + ord(char) - 64
                return n
            pos = next((i for i,c in enumerate(row) if index(re.match(r'[A-Z]+',c.attrib['r'])[0]) > index(col)), len(row))
            row.insert(pos, cell)
            self.cells[address] = cell
        return self.cells[address]

    def _value(self, address):
        c = self.cells.get(address)
        if c is None:
            return ''
        if c.attrib.get('t') == 'inlineStr':
            return ''.join(c.find(tag('is')).itertext())
        value = c.find(tag('v'))
        text = value.text or '' if value is not None else ''
        return self.strings[int(text)] if c.attrib.get('t') == 's' and text else text

    def _set(self, address, value, formula=None):
        c = self._cell(address)
        for child in list(c):
            c.remove(child)
        c.attrib.pop('t', None)
        if formula:
            ET.SubElement(c, tag('f')).text = formula
        if isinstance(value, str):
            c.set('t', 'inlineStr')
            ET.SubElement(ET.SubElement(c, tag('is')), tag('t')).text = value
        else:
            ET.SubElement(c, tag('v')).text = str(value)

    def _days(self, row):
        return [self._value(f'{chr(69+i)}{row}') in {'1', '1.0'} for i in range(15)]

    def _totals(self):
        for row in self.rows:
            self._set(f'T{row}', sum(self._days(row)), f'SUM(E{row}:S{row})')
        footer = self._place_footer()
        first, last = min(self.rows), max(self.rows)
        self._set(f'D{footer}', sum(self._value(f'D{r}').lower() == 'v' for r in self.rows), f'COUNTIFS(D{first}:D{last},"v")')
        for i in range(15):
            col = chr(69+i)
            self._set(f'{col}{footer}', sum(self._days(r)[i] for r in self.rows), f'SUM({col}{first}:{col}{last})')
        self._set(f'T{footer}', sum(sum(self._days(r)) for r in self.rows), f'SUM(T{first}:T{last})')

    def _place_footer(self):
        """Keep one total row immediately after the current account list."""
        footer = max(self.rows) + 1
        totals = [r for r in self.sheet_rows
                  if self._value(f'A{r}').strip() == 'Tổng đã hoàn thành']
        if len(totals) > 1:
            raise ValueError('Excel có nhiều dòng Tổng đã hoàn thành; hãy giữ một dòng.')
        old = totals[0] if totals else None
        if old != footer:
            occupied = self.sheet_rows.get(footer)
            if occupied is not None and any(
                    self._value(c.attrib['r']) or c.find(tag('f')) is not None
                    for c in occupied):
                raise ValueError('Dòng ngay dưới danh sách có dữ liệu; chưa di chuyển dòng tổng.')
            if old is not None:
                row = self.sheet_rows[old]
                self.data.remove(row)
                if occupied is not None:
                    self.data.remove(occupied)
                row.set('r', str(footer))
                for cell in row:
                    cell.set('r', re.sub(r'\d+$', str(footer), cell.attrib['r']))
                position = next((i for i, r in enumerate(self.data)
                                 if int(r.attrib['r']) > footer), len(self.data))
                self.data.insert(position, row)
                merges = self.sheet.find(tag('mergeCells'))
                if merges is not None:
                    for merge in merges:
                        match = re.fullmatch(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', merge.attrib['ref'])
                        if match and int(match[2]) == old and int(match[4]) == old:
                            merge.set('ref', f'{match[1]}{footer}:{match[3]}{footer}')
                self.sheet_rows = {int(r.attrib['r']): r for r in self.data}
                self.cells = {c.attrib['r']: c for r in self.data for c in r}
            else:
                self._set(f'A{footer}', 'Tổng đã hoàn thành')
            dimension = self.sheet.find(tag('dimension'))
            if dimension is not None:
                end = dimension.attrib.get('ref', 'A1:T1').split(':')[-1]
                match = re.fullmatch(r'([A-Z]+)(\d+)', end)
                if match and footer > int(match[2]):
                    start = dimension.attrib['ref'].split(':')[0]
                    dimension.set('ref', f'{start}:{match[1]}{footer}')
        return footer

    def _save(self):
        # tempfile.mkstemp retries PermissionError repeatedly on Windows.
        # One explicit, exclusive file makes permission failures immediate.
        temporary = self.path.with_name(self.path.name + '.tmp')
        created = False
        try:
            with temporary.open('xb') as stream:
                created = True
                with zipfile.ZipFile(stream, 'w') as archive:
                    for name, (info, content) in self.parts.items():
                        archive.writestr(info, self._serialize_sheet() if name == self.sheet_path else content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if created and temporary.exists():
                temporary.unlink()

    def _serialize_sheet(self):
        # mc:Ignorable contains prefix names as text, which ElementTree does
        # not rewrite or preserve automatically when serializing namespaces.
        namespaces = dict(self.namespaces)
        for prefix, uri in namespaces.items():
            if not re.fullmatch(r'ns\d+', prefix):
                ET.register_namespace(prefix, uri)
        for prefix, uri in KNOWN_NAMESPACES.items():
            ET.register_namespace(prefix, uri)
        required = set()
        for node in self.sheet.iter():
            required.update(node.attrib.get('{' + MC + '}Ignorable', '').split())
        for prefix in required:
            if prefix not in namespaces:
                if prefix not in KNOWN_NAMESPACES:
                    raise ValueError(f'Excel thiếu khai báo namespace {prefix}; chưa lưu thay đổi.')
                namespaces[prefix] = KNOWN_NAMESPACES[prefix]
        content = ET.tostring(self.sheet, encoding='utf-8', xml_declaration=True)
        declared = dict(pair for _, pair in ET.iterparse(io.BytesIO(content), events=['start-ns']))
        additions = ''.join(
            f' xmlns:{prefix}={quoteattr(uri)}' if prefix else f' xmlns={quoteattr(uri)}'
            for prefix, uri in namespaces.items() if prefix not in declared)
        if additions:
            end = content.index(b'>', content.index(b'?>') + 2)
            content = content[:end] + additions.encode('utf-8') + content[end:]
        ET.fromstring(content)
        return content

    def claim(self, script, owner, *, stt=None, allowed_stts=None):
        with self.lock:
            self._read()
            for row in self.rows:
                if stt is not None and self._value(f'A{row}').strip() != str(stt):
                    continue
                if row in self.seen or self._value(f'D{row}').strip():
                    continue
                if allowed_stts is not None and self._value(f'A{row}').strip() not in {str(v) for v in allowed_stts}:
                    continue
                days = self._days(row)
                day = None
                if script == 'A':
                    if days[0]:
                        continue
                    day = 1
                elif script == 'B':
                    completed = sum(days)
                    if not 1 <= completed < 15:
                        continue
                    if not all(days[:completed]) or any(days[completed:]):
                        raise ValueError(f'Dòng {row}: các ngày hoàn thành không liên tiếp; hãy kiểm tra Excel.')
                    day = completed + 1
                elif script == 'C':
                    if sum(days) < 2:
                        continue
                else:
                    raise ValueError('Script phải là A, B hoặc C.')
                self._set(f'D{row}', self.status_marks[0])
                self._totals()
                self._save()
                self.seen.add(row)
                self.owners[row] = owner
                return ExcelAccount(row, self._value(f'B{row}'), self._value(f'C{row}'), day)
            return None

    def complete(self, account, owner):
        with self.lock:
            self._read()
            if self.owners.get(account.row) is not owner or self._value(f'D{account.row}').casefold() != 'x':
                raise ValueError('Hàng tài khoản không còn thuộc instance đang xử lý.')
            if account.day:
                self._set(f'{chr(68+account.day)}{account.row}', 1)
            self._set(f'D{account.row}', self.status_marks[1])
            self._totals()
            self._save()

    def mark_error(self, account, owner):
        """Persist confirmed invalid credentials without changing any day result."""
        with self.lock:
            self._read()
            status = self._value(f'D{account.row}').casefold()
            if self.owners.get(account.row) is not owner or status not in {'x', 'err'}:
                raise ValueError('Hàng tài khoản không còn thuộc instance đang xử lý.')
            if status == 'err':
                return
            self._set(f'D{account.row}', 'ERR')
            self._totals()
            self._save()

    def release_after_shutdown(self, owner):
        """Release only in-memory ownership; preserve all workbook statuses."""
        with self.lock:
            self.owners = {row: assigned for row, assigned in self.owners.items()
                           if assigned is not owner}
