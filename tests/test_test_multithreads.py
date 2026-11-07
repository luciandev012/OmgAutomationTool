import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from account_excel import AccountWorkbook
import test_multithreads as script
from emulator_instances import Instance
from test_account_excel import create_book


class TestWorkbookIsolation(unittest.TestCase):
    def test_reset_clears_status_and_all_days_preserves_credentials_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source=folder/'account.xlsx';test=folder/'test_script.xlsx'
            create_book(source,[2]*10);test.write_bytes(source.read_bytes())
            before=hashlib.sha256(source.read_bytes()).digest()
            book=AccountWorkbook(test)
            for row,status in zip(book.rows,['x','V','err']*3+['X']):book._set(f'D{row}',status)
            book._set('S11',91);book._save()
            credentials=[(book._value(f'B{r}'),book._value(f'C{r}')) for r in book.rows]
            result=script.reset_test_workbook(test,folder/'backups')
            book._read()
            self.assertEqual(result['statuses_cleared'],10)
            self.assertTrue(Path(result['backup']).is_file())
            self.assertEqual([(book._value(f'B{r}'),book._value(f'C{r}')) for r in book.rows],credentials)
            for row in book.rows:
                self.assertEqual(book._value(f'D{row}'),'')
                self.assertEqual([book._value(f'{chr(69+i)}{row}') for i in range(15)],['']*15)
                self.assertEqual(book._value(f'T{row}'),'0')
            self.assertEqual(book._value('D12'),'0')
            self.assertEqual(book._value('T12'),'0')
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),before)

    def test_production_filename_is_rejected_before_it_is_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'account.xlsx';create_book(source,[1]*10)
            before=source.read_bytes()
            with self.assertRaises(ValueError):script.reset_test_workbook(source)
            self.assertEqual(source.read_bytes(),before)

    def test_reset_refuses_wrong_account_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test_script.xlsx';create_book(path,[1]*11)
            book=AccountWorkbook(path);before=path.read_bytes()
            with self.assertRaises(ValueError):book.reset_test_progress()
            self.assertEqual(path.read_bytes(),before)

    def test_dry_run_has_no_reset_or_game_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test_script.xlsx';create_book(path,[0]*10)
            provider=Mock(kind='mumu')
            provider.instances.return_value=[Instance('0','A'),Instance('1','B')]
            with patch.object(script,'TEST_WORKBOOK',path),patch.object(script,'detect_emulators',return_value=[provider]),patch.object(script,'reset_test_workbook') as reset,patch.object(script,'ExcelLoginTest') as launch:
                self.assertEqual(script.main(['--dry-run']),0)
            reset.assert_not_called();launch.assert_not_called()
