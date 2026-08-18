from fastapi import Depends
from starlette.requests import Request

from app.dependencies import get_settings
from app.helpers.authorisation import Permission
from app.settings import Settings


def is_authorised(permission: Permission, request: Request, settings: Settings = Depends(get_settings)):
    """
    Mock function for is_authorised which return true if the incoming email matches the test email for a given
    permission. Everything in this function must be contained within the function as it is patched in during tests
    so test emails must be defined within function.
    """
    email = request.headers.get('x-email')
    if permission == Permission.SUBMIT:
        return email == 'submitter@test.net'
    if permission == Permission.SENSITIVE:
        return email == 'sensitive@test.net'

    return False


def get_user_id(request: Request, settings: Settings = Depends(get_settings)):
    """
    Mock function for get_user_id which return 1 if the incoming email matches the test email for submission, or None
    otherwise.
    """
    email = request.headers.get('x-email')

    return 1 if email == 'submitter@test.net' else None
