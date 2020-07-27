import json


"""
  Logger functions for fhir/server module
"""


# For use in authentication.py
def log_fhir_id_not_matched(logger, mbi_hash, hicn_hash,
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


def log_fhir_id_matched(logger, fhir_id, mbi_hash, hicn_hash,
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
