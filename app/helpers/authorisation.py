from enum import Enum
from urllib.parse import urljoin

import requests
from fastapi import Depends
from requests import RequestException
from starlette.requests import Request

from app.dependencies import get_settings
from app.settings import Settings


class Permission(str, Enum):
    SUBMIT = 'data-submission'
    SENSITIVE = 'special-data-view'
    RESTRICTED = 'restricted-data-view'
    FULL_DATA_DOWNLOAD = 'data-download'


def is_authorised(permission: Permission, request: Request, settings: Settings = Depends(get_settings)):
    if settings.dev_auth:
        return True

    email = request.headers.get('x-email')

    if email is None or settings.authz_api_url is None:
        return False

    try:
        response = requests.get(urljoin(settings.authz_api_url, 'has-access'),
                                {'perm': permission, 'email': email}, verify=False)
    except RequestException:
        return False

    response_json = response.json()

    return response_json if type(response_json) == bool else response_json == "true"


def get_user_id(request: Request, settings: Settings = Depends(get_settings)):
    if settings.dev_auth:
        return settings.dev_auth_user_id

    email = request.headers.get('x-email')

    if email is None or settings.authz_api_url is None:
        return None

    try:
        response = requests.get(urljoin(settings.authz_api_url, 'get-user-id'),
                                {'email': email}, verify=False)
    except RequestException:
        return None

    response_json = response.json()

    return response_json['id']
