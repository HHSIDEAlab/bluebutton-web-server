import logging
import requests
import random
import urllib.request as urllib_request
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.http import JsonResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from rest_framework.exceptions import NotFound
from urllib.parse import (
    urlsplit,
    urlunsplit,
)
from apps.dot_ext.models import Approval, AuthFlowUuid
from apps.fhir.bluebutton.exceptions import UpstreamServerException
from apps.fhir.bluebutton.models import hash_hicn, hash_mbi
from .authorization import OAuth2Config
from .models import (
    AnonUserState,
    get_and_update_user,
)
from .signals import response_hook
from .validators import is_mbi_format_valid, is_mbi_format_synthetic

logger = logging.getLogger('hhs_server.%s' % __name__)
authenticate_logger = logging.getLogger('audit.authenticate.sls')


# For SLS auth workflow info, see apps/mymedicare_db/README.md
def authenticate(request):
    # Get auth_uuid from AuthFlowUuid instance via state, if available.
    state = request.GET.get('state', None)
    if state:
        try:
            auth_flow_uuid = AuthFlowUuid.objects.get(state=state)
            request.session['auth_uuid'] = str(auth_flow_uuid.auth_uuid)
        except AuthFlowUuid.DoesNotExist:
            pass

    # Create authorization flow trace UUID, if not existing from dispatch()
    if request.session.get('auth_uuid', None) is None:
        request.session['auth_uuid'] = str(uuid.uuid4())

    code = request.GET.get('code')
    if not code:
        raise ValidationError('The code parameter is required')

    sls_client = OAuth2Config()

    try:
        sls_client.exchange(code)
    except requests.exceptions.HTTPError as e:
        logger.error("Token request response error {reason}".format(reason=e))
        raise UpstreamServerException('An error occurred connecting to account.mymedicare.gov')

    userinfo_endpoint = getattr(
        settings,
        'SLS_USERINFO_ENDPOINT',
        'https://test.accounts.cms.gov/v1/oauth/userinfo')

    headers = sls_client.auth_header()
    headers.update({"X-Request-ID": getattr(request, '__logging_uuid', None)})
    response = requests.get(userinfo_endpoint,
                            headers=headers,
                            verify=sls_client.verify_ssl,
                            hooks={'response': response_hook})

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error("User info request response error {reason}".format(reason=e))
        raise UpstreamServerException(
            'An error occurred connecting to account.mymedicare.gov')

    # Get the userinfo response object
    user_info = response.json()

    # Add MBI validation info for logging.
    sls_mbi = user_info.get("mbi", "").upper()
    sls_mbi_format_valid, sls_mbi_format_msg = is_mbi_format_valid(sls_mbi)
    sls_mbi_format_synthetic = is_mbi_format_synthetic(sls_mbi)

    # If MBI returned from SLS is blank, set to None for hash logging
    if sls_mbi == "":
        sls_mbi = None

    # TODO: when rebasing with BB2-132 change '' for auth_uuid to None
    authenticate_logger.info({
        "type": "Authentication:start",
        "auth_uuid": request.session.get('auth_uuid', ''),
        "sub": user_info["sub"],
        "sls_mbi_format_valid": sls_mbi_format_valid,
        "sls_mbi_format_msg": sls_mbi_format_msg,
        "sls_mbi_format_synthetic": sls_mbi_format_synthetic,
        "sls_hicn_hash": hash_hicn(user_info['hicn']),
        "sls_mbi_hash": hash_mbi(sls_mbi),
    })

    user = get_and_update_user(user_info, request)

    # TODO: when rebasing with BB2-132 change '' for auth_uuid to None
    authenticate_logger.info({
        "type": "Authentication:success",
        "auth_uuid": request.session.get('auth_uuid', ''),
        "sub": user_info["sub"],
        "user": {
            "id": user.id,
            "username": user.username,
            "crosswalk": {
                "id": user.crosswalk.id,
                "user_hicn_hash": user.crosswalk.user_hicn_hash,
                "user_mbi_hash": user.crosswalk.user_mbi_hash,
                "fhir_id": user.crosswalk.fhir_id,
                "user_id_type": user.crosswalk.user_id_type,
            },
        },
    })
    request.user = user


@never_cache
def callback(request):
    try:
        authenticate(request)
    except ValidationError as e:
        return JsonResponse({
            "error": e.message,
        }, status=400)
    except NotFound as e:
        return TemplateResponse(
            request,
            "bene_404.html",
            context={
                "error": e.detail,
            },
            status=404)
    except UpstreamServerException as e:
        return JsonResponse({
            "error": e.detail,
        }, status=502)

    state = request.GET.get('state')
    if not state:
        return JsonResponse({
            "error": 'The state parameter is required'
        }, status=400)

    try:
        anon_user_state = AnonUserState.objects.get(state=state)
    except AnonUserState.DoesNotExist:
        return JsonResponse({"error": 'The requested state was not found'}, status=400)
    next_uri = anon_user_state.next_uri

    scheme, netloc, path, query_string, fragment = urlsplit(next_uri)

    approval = Approval.objects.create(
        user=request.user)

    # Only go back to app authorization
    auth_uri = reverse('oauth2_provider:authorize-instance', args=[approval.uuid])
    _, _, auth_path, _, _ = urlsplit(auth_uri)

    return HttpResponseRedirect(urlunsplit((scheme, netloc, auth_path, query_string, fragment)))


def generate_nonce(length=26):
    """Generate pseudo-random number."""
    return ''.join([str(random.randint(0, 9)) for i in range(length)])


@never_cache
def mymedicare_login(request):
    redirect = settings.MEDICARE_REDIRECT_URI
    mymedicare_login_url = settings.MEDICARE_LOGIN_URI
    redirect = urllib_request.pathname2url(redirect)
    state = generate_nonce()
    state = urllib_request.pathname2url(state)
    request.session['state'] = state
    mymedicare_login_url = "%s&state=%s&redirect_uri=%s" % (
        mymedicare_login_url, state, redirect)
    next_uri = request.GET.get('next', "")

    AnonUserState.objects.create(state=state, next_uri=next_uri)

    # Create AuthFlowUuid instance to pass along auth_uuid using state.
    auth_uuid = request.session.get('auth_uuid', None)
    if auth_uuid:
        try:
            AuthFlowUuid.objects.create(state=state, auth_uuid=auth_uuid, code=None)
        except IntegrityError:
            pass

    return HttpResponseRedirect(mymedicare_login_url)
