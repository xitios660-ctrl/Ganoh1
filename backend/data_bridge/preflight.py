"""Read-only credential preflight for the private backup executor.

Atlas project/cluster scopes must ALSO be checked with its control-plane inventory.
This check verifies the actual authenticated MongoDB connection, not an attestation.
"""
from pymongo.errors import PyMongoError
from backend.data_bridge.archive import ArchiveError


def require_backup_reader(client, username):
    if not isinstance(username,str) or not username:
        raise ArchiveError('Usuário dedicado de backup obrigatório')
    try:
        result=client.admin.command({'connectionStatus':1,'showPrivileges':False})
    except PyMongoError:
        raise ArchiveError('Não foi possível conferir as permissões da conexão de backup') from None
    info=result.get('authInfo',{})
    users=info.get('authenticatedUsers',[])
    roles=info.get('authenticatedUserRoles',[])
    if users != [{'user':username,'db':'admin'}]:
        raise ArchiveError('A conexão não corresponde ao usuário dedicado informado')
    if roles != [{'role':'read','db':'ganoh_production'}]:
        raise ArchiveError('Backup exige somente read em ganoh_production; conta com outras funções recusada')
    return {'verified':True,'database':'ganoh_production','role':'read'}
