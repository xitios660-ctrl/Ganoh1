import unittest
from copy import deepcopy
from unittest.mock import Mock
from pymongo.errors import OperationFailure
from backend.data_bridge.archive import ArchiveError
from backend.data_bridge.preflight import require_backup_reader


class BackupPreflightTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock()
        self.info={'authenticatedUsers':[{'user':'fixture-reader','db':'admin'}],
                   'authenticatedUserRoles':[{'role':'read','db':'ganoh_production'}]}

    def check(self,info):
        self.client.admin.command.return_value={'authInfo':info}
        return require_backup_reader(self.client,'fixture-reader')

    def test_actual_authenticated_read_role_is_required_without_reading_records(self):
        self.assertTrue(self.check(self.info)['verified'])
        self.client.admin.command.assert_called_once_with({'connectionStatus':1,'showPrivileges':False})

    def test_admin_write_other_database_and_missing_authentication_are_rejected(self):
        for roles in ([],[{'role':'atlasAdmin','db':'admin'}],
                      [{'role':'readWrite','db':'ganoh_production'}],
                      [{'role':'read','db':'other_database'}],
                      self.info['authenticatedUserRoles']+[{'role':'atlasAdmin','db':'admin'}]):
            info=deepcopy(self.info);info['authenticatedUserRoles']=roles
            with self.assertRaises(ArchiveError):self.check(info)
        for users in ([],[{'user':'different','db':'admin'}],
                      [{'user':'fixture-reader','db':'other_database'}]):
            info=deepcopy(self.info);info['authenticatedUsers']=users
            with self.assertRaises(ArchiveError):self.check(info)

    def test_remote_error_body_and_credentials_are_not_propagated(self):
        self.client.admin.command.side_effect=OperationFailure('FIXTURE-SECRET-SERVER-ERROR')
        with self.assertRaises(ArchiveError) as error:require_backup_reader(self.client,'fixture-reader')
        self.assertNotIn('FIXTURE-SECRET',str(error.exception))
