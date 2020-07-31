import requests
from django.conf import settings
from rest_framework import exceptions
from ..bluebutton.exceptions import UpstreamServerException
from ..bluebutton.utils import (FhirServerAuth,
                                get_resourcerouter)
from .loggers import log_match_fhir_id


def search_fhir_id_by_identifier_mbi_hash(mbi_hash):
    """
        Search the backend FHIR server's patient resource
        using the mbi_hash identifier.
    """
    search_identifier = settings.FHIR_SEARCH_PARAM_IDENTIFIER_MBIHASH \
        + "%7C" + mbi_hash

    return search_fhir_id_by_identifier(search_identifier)


def search_fhir_id_by_identifier_hicn_hash(hicn_hash):
    """
        Search the backend FHIR server's patient resource
        using the hicn_hash identifier.
    """
    search_identifier = settings.FHIR_SEARCH_PARAM_IDENTIFIER_HICNHASH \
        + "%7C" + hicn_hash

    return search_fhir_id_by_identifier(search_identifier)


def search_fhir_id_by_identifier(search_identifier):
    """
        Search the backend FHIR server's patient resource
        using the specified identifier.

        Return:  fhir_id = matched ID (or None).
                 err_mesg = None or related error message.
    """
    # Get certs from FHIR server settings
    auth_settings = FhirServerAuth(None)
    certs = (auth_settings['cert_file'], auth_settings['key_file'])

    # Build URL with patient ID search by identifier.
    url = get_resourcerouter().fhir_url \
        + "Patient/?identifier=" + search_identifier \
        + "&_format=" + settings.FHIR_PARAM_FORMAT

    # Get FHIR service backend response.
    #   TODO: Should work with verify=True
    response = requests.get(url, cert=certs, verify=False)
    response.raise_for_status()
    backend_data = response.json()

    # Parse and validate backend_data response.
    if (
        'entry' in backend_data
            and backend_data.get('total', 0) == 1
            and len(backend_data.get('entry', '')) == 1
    ):
        # Found a single matching ID.
        fhir_id = backend_data['entry'][0]['resource']['id']
        return fhir_id, None
    elif (
        'entry' in backend_data
            and (backend_data.get('total', 0) > 1 or len(backend_data.get('entry', '')) > 1)
    ):
        # Has duplicate beneficiary IDs.
        return None, "Duplicate beneficiaries found in Patient resource bundle"
    else:
        # Not found.
        return None, None


def match_fhir_id(mbi_hash, hicn_hash):
    """
      Matches a patient identifier via the backend FHIR server
      using an MBI or HICN hash.

      Summary:
        - Perform primary lookup using mbi_hash.
        - If there is an mbi_hash lookup issue, raise exception.
        - Perform secondary lookup using HICN_HASH
        - If there is a hicn_hash lookup issue, raise exception.
        - A NotFound exception is raised, if no match was found.
      Returns:
        fhir_id = Matched patient identifier.
        hash_lookup_type = The type used for the successful lookup (M or H).
      Raises exceptions:
        UpstreamServerException: If hicn_hash or mbi_hash search found duplicates.
        NotFound: If both searches did not match a fhir_id.
    """
    # Perform primary lookup using MBI_HASH
    if mbi_hash is not None:
        fhir_id, err_mesg = search_fhir_id_by_identifier_mbi_hash(mbi_hash)
        if fhir_id is not None:
            log_match_fhir_id(fhir_id, mbi_hash, hicn_hash, True, "M",
                              "FOUND beneficiary via mbi_hash")
            return fhir_id, "M"
        elif err_mesg is not None:
            log_match_fhir_id(fhir_id, mbi_hash, hicn_hash, False, "M", err_mesg)
            # Don't return a 404 because retrying later will not fix this.
            raise UpstreamServerException(err_mesg)

    # Perform secondary lookup using HICN_HASH
    fhir_id, err_mesg = search_fhir_id_by_identifier_hicn_hash(hicn_hash)
    if fhir_id is not None:
        log_match_fhir_id(fhir_id, mbi_hash, hicn_hash, True, "H",
                          "FOUND beneficiary via hicn_hash")
        return fhir_id, "H"
    elif err_mesg is not None:
        log_match_fhir_id(fhir_id, mbi_hash, hicn_hash, False, "H", err_mesg)
        # Don't return a 404 because retrying later will not fix this.
        raise UpstreamServerException(err_mesg)
    else:
        log_match_fhir_id(fhir_id, mbi_hash, hicn_hash, False, None,
                          "FHIR ID NOT FOUND for both mbi_hash and hicn_hash")
        raise exceptions.NotFound("The requested Beneficiary has no entry, however this may change")
