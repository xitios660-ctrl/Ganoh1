import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


class UnsafeImporterRetirement(unittest.TestCase):
    def test_old_entrypoint_does_not_read_secrets_or_open_database(self):
        file=Path(__file__).resolve().parents[2]/'import_from_prod.py'
        spec=importlib.util.spec_from_file_location('retired_importer',file)
        module=importlib.util.module_from_spec(spec)
        with patch('pymongo.MongoClient',side_effect=AssertionError('No production client')):
            spec.loader.exec_module(module)
            with self.assertRaises(SystemExit):module.main()
