import json
import requests
import logging
from rest_framework import exceptions
from ..bluebutton.exceptions import UpstreamServerException
from ..bluebutton.utils import (FhirServerAuth,
                                get_resourcerouter)

logger = logging.getLogger('hhs_server.%s' % __name__)


def log_fhir_id_not_matched(mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg):
    '''
        Logging for "FhirIDNotFound" type
        used in match_backend_patient_identifier()
    '''
    logger.info(json.dumps({
        "type": "FhirIDNotFound",
        "mbi_hash": mbi_hash,
        "hicn_hash": hicn_hash,
        "hash_lookup_type": hash_lookup_type,
        "hash_lookup_mesg": hash_lookup_mesg,
    }))


def log_fhir_id_matched(fhir_id, mbi_hash, hicn_hash,
                        hash_lookup_type, hash_lookup_mesg):
    '''
        Logging for "FhirIDFound" type
        used in match_backend_patient_identifier()
    '''
    logger.info(json.dumps({
        "type": "FhirIDFound",
        "fhir_id": fhir_id,
        "mbi_hash": mbi_hash,
        "hicn_hash": hicn_hash,
        "hash_lookup_type": hash_lookup_type,
        "hash_lookup_mesg": hash_lookup_mesg,
    }))


def match_backend_patient_identifier(mbi_hash, hicn_hash):
    '''
    Matches a patient identifier via the backend FHIR server
    using an MBI or HICN hash.

    Summary:
        1. mbi_hash is used for the initial lookup.
        2. If there is a mbi lookup issue, the hicn_hash is used next.
        3. If there is a hicn lookup issue, exceptions are raised.
        4. A NotFound exception is raised if no match was found.

    Returns:
        fhir_id = Matched patient identifier.
        backend_data = Passed thru to caller. Utilized in TestAuthentication.
        hash_lookup_type = The type used for the successful lookup (M or H).

    Raises:
        UpstreamServerException: If hicn_hash search found duplicates.
        NotFound: If both searches did not match a fhir_id.
    '''
    auth_state = FhirServerAuth(None)
    certs = (auth_state['cert_file'], auth_state['key_file'])

    # 1. mbi_hash is used for the initial lookup.
    hash_lookup_type = "M"
    hash_lookup_mesg = None

    if mbi_hash is not None:
        # URL for patient ID by mbi_hash.
        url = get_resourcerouter().fhir_url + \
            "Patient/?identifier=https%3A%2F%2Fbluebutton.cms.gov" + \
            "%2Fresources%2Fidentifier%2Fmbi-hash%7C" + \
            mbi_hash + \
            "&_format=application%2Fjson%2Bfhir"
        response = requests.get(url, cert=certs, verify=False)
        response.raise_for_status()
        backend_data = response.json()

        # Check resource bundle total > 1
        if backend_data.get('total', 0) > 1:
            hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle total"

        # Check number of resource entries > 1
        if (
            'entry' in backend_data
            and len(backend_data['entry']) > 1
            and hash_lookup_mesg is not None
        ):
            hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle entry"

        # If resource bundle has an entry and total == 1, return match results
        if (
            'entry' in backend_data
            and backend_data['total'] == 1
            and len(backend_data['entry']) == 1
            and hash_lookup_mesg is None
        ):
            fhir_id = backend_data['entry'][0]['resource']['id']
            # Log for FhirIDFound type
            hash_lookup_mesg = "FOUND beneficiary via mbi_hash"
            log_fhir_id_matched(fhir_id, mbi_hash, hicn_hash,
                                hash_lookup_type, hash_lookup_mesg)
            return fhir_id, backend_data, hash_lookup_type

    # Log for mbi FhirIDNotFound type
    if hash_lookup_mesg is None:
        # Set mesg if it was not set previously for duplicates.
        hash_lookup_mesg = "FHIR ID NOT FOUND for MBI hash lookup"
    log_fhir_id_not_matched(mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg)

    # 2. If there is a mbi lookup issue, the hicn_hash is used next.
    hash_lookup_type = "H"
    hash_lookup_mesg = None

    # URL for patient ID by hicn_hash.
    url = get_resourcerouter().fhir_url + \
        "Patient/?identifier=http%3A%2F%2Fbluebutton.cms.hhs.gov%2Fidentifier%23hicnHash%7C" + \
        hicn_hash + \
        "&_format=json"
    response = requests.get(url, cert=certs, verify=False)
    response.raise_for_status()
    backend_data = response.json()

    # 3. If there is a hicn lookup issue, exceptions are raised.
    if backend_data.get('total', 0) > 1:
        # Log for FhirIDNotFound type
        hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle total"
        log_fhir_id_not_matched(mbi_hash, hicn_hash,
                                hash_lookup_type, hash_lookup_mesg)
        # Don't return a 404 because retrying later will not fix this.
        raise UpstreamServerException(hash_lookup_mesg)

    if 'entry' in backend_data and len(backend_data['entry']) > 1:
        # Log for FhirIDNotFound type
        hash_lookup_mesg = "Duplicate beneficiaries found in Patient resource bundle entry"
        log_fhir_id_not_matched(mbi_hash, hicn_hash,
                                hash_lookup_type, hash_lookup_mesg)
        raise UpstreamServerException(hash_lookup_mesg)

    if 'entry' in backend_data and backend_data['total'] == 1:
        fhir_id = backend_data['entry'][0]['resource']['id']
        # Log for FhirIDFound type
        hash_lookup_mesg = "FOUND beneficiary via hicn_hash"
        log_fhir_id_matched(fhir_id, mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg)
        return fhir_id, backend_data, hash_lookup_type

    # Log for FhirIDNotFound type
    hash_lookup_mesg = "FHIR ID NOT FOUND for both MBI and HICN hash lookups"
    log_fhir_id_not_matched(mbi_hash, hicn_hash,
                            hash_lookup_type, hash_lookup_mesg)

    raise exceptions.NotFound("The requested Beneficiary has no entry, however this may change")
