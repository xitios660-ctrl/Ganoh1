import io
import json
import os
import secrets
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from desktop.offline_store import OfflineJournal,OfflineError
from desktop.backups import export,restore_isolated
from desktop import auth


class BackupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.key=secrets.token_bytes(32)
  self.journal=OfflineJournal(self.root/'live.sqlite','runner',encryption_key=self.key)
  self.phrase='Fixture-Recovery-Phrase-2026-Only'
  self.protect=lambda path,key:path.write_bytes(b'fixture-protected-not-a-real-key')
 def test_consistent_encrypted_backup_restores_pending_ids_and_revokes_sessions(self):
  auth.create(self.journal,'owner-demo','Long-Fixture-Password-2026',first=True)
  token=auth.login(self.journal,'owner-demo','Long-Fixture-Password-2026')
  held=self.journal._connect();self.addCleanup(held.close)
  saved=self.journal.record_sale(sale_id='fixture-secret-sale',total_cents=123,payment_method='cash',items=[{'sku':'fixture'}])
  data=export(self.journal,self.phrase)
  self.assertNotIn(b'fixture-secret-sale',data);self.assertNotIn(self.key,data)
  restored=restore_isolated(data,self.phrase,self.root/'recovered','runner',protect_key=self.protect)
  self.assertEqual(restored.pending()[0]['operation_id'],saved['operation_id'])
  self.assertEqual(restored.status()['sqlite_integrity'],'ok')
  self.assertIsNone(auth.actor(restored,token))
  self.assertIsNotNone(auth.actor(self.journal,token))
  self.assertEqual(self.journal.status()['pending'],1)
 def test_wrong_phrase_unit_and_tampering_do_not_touch_live_database(self):
  data=export(self.journal,self.phrase)
  for phrase,unit in [('wrong-password-but-long','runner'),(self.phrase,'gym-londres')]:
   with self.assertRaises(OfflineError):restore_isolated(data,phrase,self.root/'bad',unit,protect_key=self.protect)
   self.assertFalse((self.root/'bad').exists())
  source=zipfile.ZipFile(io.BytesIO(data));out=io.BytesIO()
  with source,zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as archive:
   for name in source.namelist():
    contents=source.read(name)
    if name=='journal.sqlite3':contents=contents[:-1]+bytes([contents[-1]^1])
    archive.writestr(name,contents)
  with self.assertRaises(OfflineError):restore_isolated(out.getvalue(),self.phrase,self.root/'bad','runner',protect_key=self.protect)
  self.assertEqual(self.journal.status()['sqlite_integrity'],'ok')
 def test_existing_restore_target_is_never_overwritten(self):
  data=export(self.journal,self.phrase);target=self.root/'existing';target.mkdir();(target/'keep').write_text('original')
  with self.assertRaises(FileExistsError):restore_isolated(data,self.phrase,target,'runner',protect_key=self.protect)
  self.assertEqual((target/'keep').read_text(),'original')
 @unittest.skipUnless(os.name=='nt','DPAPI requires Windows')
 def test_restored_key_reopens_under_windows_dpapi(self):
  from desktop.windows_secrets import load_secret
  data=export(self.journal,self.phrase)
  restore_isolated(data,self.phrase,self.root/'windows-restore','runner')
  key=load_secret(self.root/'windows-restore'/'database-key.dpapi')
  reopened=OfflineJournal(self.root/'windows-restore'/'journal.sqlite3','runner',encryption_key=key)
  self.assertEqual(reopened.status()['sqlite_integrity'],'ok')
