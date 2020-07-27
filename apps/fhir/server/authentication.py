import requests
import logging
from django.conf import settings
from rest_framework import exceptions
from ..bluebutton.exceptions import UpstreamServerException
from ..bluebutton.utils import (FhirServerAuth,
                                get_resourcerouter)
from .loggers import (log_fhir_id_not_matched,
                      log_fhir_id_matched)

logger = logging.getLogger('hhs_server.%s' % __name__)


def match_backend_patient_identifier(mbi_hash, hicn_hash):
    '''
    Matches a patient identifier via the backend FHIR server
    using an MBI or HICN hash.

    Summary:
        1. mbi_hash is used for the initial lookup.May be empty/None from SLS.
        2. If there is an mbi_hash lookup issue, exceptions are raised.
        3. If the mbi_hash lookup is not found, the hicn_hash is used next.
        4. If there is a hicn_hash lookup issue, exceptions are raised.
        5. A NotFound exception is raised if no match was found.

    Returns:
        fhir_id = Matched patient identifier.
        backend_data = Passed thru to caller. Utilized in TestAuthentication.
        hash_lookup_type = The type used for the successful lookup (M or H).

    Raises:
        UpstreamServerException: If hicn_hash or mbi_hash search found duplicates.
        NotFound: If both searches did not match a fhir_id.
    '''
    auth_state = FhirServerAuth(None)
    certs = (auth_state['cert_file'], auth_state['key_file'])

    # 1. mbi_hash is used for the initial lookup. May be empty/None from auth provider.
    hash_lookup_type = "M"
    hash_lookup_mesg = None

    if mbi_hash is not None:
        # URL for patient ID search by mbi_hash.
        url = get_resourcerouter().fhir_url + \
            "Patient/?identifier=" + \
            settings.FHIR_SEARCH_PARAM_IDENTIFIER_MBIHASH + "%7C" + \
            mbi_hash + \
            "&_format=" + \
            settings.FHIR_PARAM_FORMAT

        # TODO: Should work with verify=True
        response = requests.get(url, cert=certs, verify=False)
        response.raise_for_status()
        backend_data = response.json()

        # 2. If there is an mbi_hash lookup issue, exceptions are raised.

        # Check resource bundle total > 1
        if backend_data.get('total', 0) > 1:
            hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle total"
            log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
                                    hash_lookup_type, hash_lookup_mesg)
            # Don't return a 404 because retrying later will not fix this.
            raise UpstreamServerException(hash_lookup_mesg)

        # Check number of resource entries > 1
        if (
            'entry' in backend_data
            and len(backend_data['entry']) > 1
        ):
            hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle entry"
            log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
                                    hash_lookup_type, hash_lookup_mesg)
            raise UpstreamServerException(hash_lookup_mesg)

        # If resource bundle has an entry and total == 1, return match results
        if (
            'entry' in backend_data
            and backend_data['total'] == 1
            and len(backend_data['entry']) == 1
        ):
            fhir_id = backend_data['entry'][0]['resource']['id']
            # Log for FhirIDFound type
            hash_lookup_mesg = "FOUND beneficiary via mbi_hash"
            log_fhir_id_matched(logger, fhir_id, mbi_hash, hicn_hash,
                                hash_lookup_type, hash_lookup_mesg)
            return fhir_id, backend_data, hash_lookup_type

    # Log for mbi_hash FhirIDNotFound type
    if hash_lookup_mesg is None:
        # Set mesg if it was not set previously for duplicates.
        hash_lookup_mesg = "FHIR ID NOT FOUND for MBI hash lookup"
    log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg)

    # 3. If the mbi_hash lookup is not found, the hicn_hash is used next.
    hash_lookup_type = "H"
    hash_lookup_mesg = None

    # URL for patient ID search by hicn_hash.
    url = get_resourcerouter().fhir_url + \
        "Patient/?identifier=" + \
        settings.FHIR_SEARCH_PARAM_IDENTIFIER_HICNHASH + "%7C" + \
        hicn_hash + \
        "&_format=" + \
        settings.FHIR_PARAM_FORMAT

    response = requests.get(url, cert=certs, verify=False)
    response.raise_for_status()
    backend_data = response.json()

    # 4. If there is a hicn_hash lookup issue, exceptions are raised.
    if backend_data.get('total', 0) > 1:
        # Log for FhirIDNotFound type
        hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle total"
        log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
                                hash_lookup_type, hash_lookup_mesg)
        # Don't return a 404 because retrying later will not fix this.
        raise UpstreamServerException(hash_lookup_mesg)

    if 'entry' in backend_data and len(backend_data['entry']) > 1:
        # Log for FhirIDNotFound type
        hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle entry"
        log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
                                hash_lookup_type, hash_lookup_mesg)
        raise UpstreamServerException(hash_lookup_mesg)

    if 'entry' in backend_data and backend_data['total'] == 1:
        fhir_id = backend_data['entry'][0]['resource']['id']
        # Log for FhirIDFound type
        hash_lookup_mesg = "FOUND beneficiary via hicn_hash"
        log_fhir_id_matched(logger, fhir_id, mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg)
        return fhir_id, backend_data, hash_lookup_type

    # 5. A NotFound exception is raised if no match was found.
    hash_lookup_mesg = "FHIR ID NOT FOUND for both MBI and HICN hash lookups"
    log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg)
    raise exceptions.NotFound("The requested Beneficiary has no entry, however this may change")
