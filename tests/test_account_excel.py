from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
import zipfile
import io
from unittest.mock import patch, Mock

from account_excel import AccountWorkbook, ExcelAccount, tag
from excel_scripts import ScriptBatch, ExcelCycle
from task_sessions import InstanceSession


def create_book(path, days):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    root=ET.Element(tag('worksheet')); data=ET.SubElement(root,tag('sheetData'))
    def row(n,values):
        r=ET.SubElement(data,tag('row'),r=str(n))
        for i,v in enumerate(values):
            if v is None: continue
            c=ET.SubElement(r,tag('c'),r=f'{chr(65+i)}{n}',t='inlineStr')
            ET.SubElement(ET.SubElement(c,tag('is')),tag('t')).text=str(v)
    row(1,['STT','TK','MK','Status']+list(range(1,16))+['Hoàn Thành'])
    for i,count in enumerate(days,2):
        row(i,[i-1,f'user{i}','password',None]+[1 if j<count else None for j in range(15)]+[count])
    row(len(days)+2,['Tổng đã hoàn thành'])
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',ET.tostring(root))


class AccountExcelTests(unittest.TestCase):
    def test_cycle_does_not_restart_game_before_login_from_notice(self):
        session=InstanceSession('A');session.connection=('adb','A')
        with patch('excel_scripts.AdbDevice') as device, patch('excel_scripts.LoginEngine') as engine:
            engine.return_value.run.return_value=Mock(status='failed',message='stop fixture')
            cycle=ExcelCycle(session,Mock(),Mock(),'com.gs2.omg',Mock())
            with self.assertRaisesRegex(ValueError,'stop fixture'):
                cycle.run(ExcelAccount(2,'user','password',1))
            device.return_value.launch.assert_not_called()
            self.assertFalse(engine.return_value.run.call_args.kwargs['reset'])

    def test_save_preserves_namespace_used_only_by_ignorable_text(self):
        book=self.book([0])
        with zipfile.ZipFile(self.path) as z:
            parts={name:z.read(name) for name in z.namelist()}
        root=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        root.set('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable','xr')
        xml=ET.tostring(root)
        pos=xml.index(b'>')
        xml=xml[:pos]+b' xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"'+xml[pos:]
        parts['xl/worksheets/sheet1.xml']=xml
        with zipfile.ZipFile(self.path,'w') as z:
            for name,content in parts.items():z.writestr(name,content)
        AccountWorkbook(self.path)
        with zipfile.ZipFile(self.path) as z:xml=z.read('xl/worksheets/sheet1.xml')
        declarations=dict(v for _,v in ET.iterparse(io.BytesIO(xml),events=['start-ns']))
        self.assertIn('xr',declarations)

    def test_repairs_legacy_renamed_x14ac_without_changing_account_data(self):
        book=self.book([0])
        with zipfile.ZipFile(self.path) as z:parts={name:z.read(name) for name in z.namelist()}
        root=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        root.set('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable','x14ac')
        root.set('{http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac}dyDescent','0.25')
        ET.register_namespace('x14ac','http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac')
        xml=ET.tostring(root).replace(b'xmlns:x14ac=',b'xmlns:ns9=').replace(b' x14ac:dyDescent=',b' ns9:dyDescent=')
        parts['xl/worksheets/sheet1.xml']=xml
        with zipfile.ZipFile(self.path,'w') as z:
            for name,content in parts.items():z.writestr(name,content)
        repaired=AccountWorkbook(self.path)
        with zipfile.ZipFile(self.path) as z:xml=z.read('xl/worksheets/sheet1.xml')
        declarations=dict(v for _,v in ET.iterparse(io.BytesIO(xml),events=['start-ns']))
        self.assertIn('x14ac',declarations)
        self.assertEqual((repaired._value('B2'),repaired._value('C2')),('user2','password'))

    def test_permission_failure_is_immediate_and_original_is_unchanged(self):
        book=self.book([0])
        original=self.path.read_bytes()
        with patch.object(Path,'open',side_effect=PermissionError('write denied')):
            with self.assertRaises(PermissionError):
                book._save()
        self.assertEqual(self.path.read_bytes(),original)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'account.xlsx'
    def tearDown(self): self.temp.cleanup()

    def book(self, days):
        create_book(self.path,days)
        return AccountWorkbook(self.path)

    def test_parallel_claims_are_saved_as_x_before_work_and_distinct(self):
        book=self.book([0,0]); owners=[object(),object()]
        barrier=threading.Barrier(2)
        def claim(owner):
            barrier.wait(); return book.claim('A',owner)
        with ThreadPoolExecutor(2) as pool: rows=list(pool.map(claim,owners))
        self.assertEqual({r.row for r in rows},{2,3})
        book._read(); self.assertEqual([book._value(f'D{r}') for r in (2,3)],['x','x'])

    def test_completion_updates_v_day_and_both_sums_in_one_save(self):
        book=self.book([1]); owner=object(); account=book.claim('B',owner)
        self.assertEqual(account.day,2)
        book.complete(account,owner)
        book._read()
        self.assertEqual([book._value(c) for c in ('D2','F2','T2','F3','T3')],['v','1','2','1','2'])

    def test_b_and_c_use_real_horizontal_sum_instead_of_stale_formula_cache(self):
        book=self.book([0,1,2,15])
        self.assertEqual(book.claim('B',object()).row,3)
        self.assertEqual(book.claim('C',object()).row,4)
        self.assertEqual(book.claim('C',object()).row,5)

    def test_clear_only_own_rows_after_shutdown_and_never_reclaim_same_run(self):
        book=self.book([2,2]); a,b=object(),object()
        first,second=book.claim('C',a),book.claim('C',b)
        book.complete(first,a); book.release_after_shutdown(a)
        book._read(); self.assertEqual(book._value(f'D{first.row}'),'')
        self.assertEqual(book._value(f'D{second.row}'),'x')
        self.assertIsNone(book.claim('C',b))
        self.assertEqual(book._value(f'T{first.row}'),'2')

    def test_status_x_and_v_are_skipped(self):
        book=self.book([0,0,0]); book._set('D2','x');book._set('D3','v');book._save()
        self.assertEqual(book.claim('A',object()).row,4)

    def test_script_c_completes_without_writing_a_day(self):
        book=self.book([2]); owner=object(); item=book.claim('C',owner)
        book.complete(item,owner);book._read()
        self.assertEqual(book._value('D2'),'v');self.assertEqual(book._value('G2'),'')
        self.assertEqual(book._value('T2'),'2')

    def test_failure_never_marks_completed_or_releases(self):
        book=self.book([0]); s=InstanceSession('A');s.connection=('adb','A');s.begin()
        class Cycle:
            def run(self,account): raise ValueError('Not back at notice')
        shutdown=[]
        result=ScriptBatch(book,'A',[s],lambda _:Cycle(),lambda _:shutdown.append(1),lambda *_:None).run()
        book._read();self.assertEqual(book._value('D2'),'x');self.assertEqual(book._value('E2'),'')
        self.assertEqual(shutdown,[]);self.assertFalse(result[0]['closed'])

    def test_two_workers_reserve_then_complete_before_shutdown_and_release(self):
        book=self.book([0,0]); barrier=threading.Barrier(2);events=[];lock=threading.Lock()
        sessions=[InstanceSession('A'),InstanceSession('B')]
        for s in sessions:s.connection=('adb',s.name);s.begin()
        class Cycle:
            def run(self,account):
                barrier.wait(timeout=2)
                with book.lock:
                    book._read()
                    assert book._value('D2')=='x' and book._value('D3')=='x'
                barrier.wait(timeout=2)
        def shutdown(s):
            with book.lock:
                book._read()
                assert all(book._value(f'D{r}')=='v' for r,o in book.owners.items() if o is s)
        result=ScriptBatch(book,'A',sessions,lambda _:Cycle(),shutdown,lambda *_:None).run()
        self.assertEqual(sum(r['completed'] for r in result),2)
        self.assertTrue(all(r['closed'] for r in result))
        book._read();self.assertEqual(book._value('D2'),'');self.assertEqual(book._value('D3'),'')
        self.assertEqual(book._value('E4'),'2')
