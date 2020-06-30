import json
import logging
from django.db import models, transaction
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from apps.accounts.models import UserProfile
from apps.fhir.server.authentication import match_backend_patient_identifier
from apps.fhir.bluebutton.models import Crosswalk, hash_hicn, hash_mbi

logger = logging.getLogger('hhs_server.%s' % __name__)


def log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg):
    '''
        Logging for info or issue
        used in get_and_update_user()
        mesg = Description text.
    '''
    logger.info(json.dumps({
        "type": "mymedicare_cb:get_and_update_user",
        "fhir_id": fhir_id,
        "mbi_hash": mbi_hash,
        "hicn_hash": hicn_hash,
        "hash_lookup_type": hash_lookup_type,
        "crosswalk":
            {
                "id": user.crosswalk.id,
                "user_hicn_hash": user.crosswalk.user_hicn_hash,
                "user_mbi_hash": user.crosswalk.user_mbi_hash,
                "fhir_id": user.crosswalk.fhir_id,
                "user_id_type": user.crosswalk.user_id_type,
            },
            "mesg": mesg,
    }))


def log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg):
    '''
        Logging for info or issue
        used in create_beneficiary_record()
        mesg = Description text.
    '''
    logger.info(json.dumps({
        "type": "mymedicare_cb:create_beneficiary_record",
        "username": username,
        "fhir_id": fhir_id,
        "user_mbi_hash": user_mbi_hash,
        "user_hicn_hash": user_hicn_hash,
        "mesg": mesg,
    }))


def get_and_update_user(user_info):
    """
    Find or create the user associated
    with the identity information from the ID provider.

    Args:
        user_info: Identity response from the userinfo endpoint of the ID provider.

    Returns:
        A User

    Raises:
        KeyError: If an expected key is missing from user_info.
        KeyError: If response from fhir server is malformed.
        AssertionError: If a user is matched but not all identifiers match.
    """
    subject = user_info['sub']
    hicn = user_info['hicn']
    # Convert SLS's mbi to UPPER case.
    mbi = user_info['mbi'].upper()

    # If mbi is empty set to None
    if mbi == "":
        mbi = None

    # Create hashed values.
    hicn_hash = hash_hicn(hicn)
    mbi_hash = hash_mbi(mbi)

    # Match a patient identifier via the backend FHIR server
    fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(mbi_hash=mbi_hash, hicn_hash=hicn_hash)

    try:
        # Does an existing user and crosswalk exist for SLS username?
        user = User.objects.get(username=subject)

        # Log pre asserts.
        if user.crosswalk.user_hicn_hash != hicn_hash:
            mesg = "Found user's hicn did not match"
            log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)

        if user.crosswalk.fhir_id != fhir_id:
            mesg = "Found user's fhir_id did not match"
            log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)

        assert user.crosswalk.user_hicn_hash == hicn_hash, "Found user's hicn did not match"
        assert user.crosswalk.fhir_id == fhir_id, "Found user's fhir_id did not match"

        if user.crosswalk.user_mbi_hash is not None:
            if user.crosswalk.user_mbi_hash != mbi_hash:
                mesg = "Found user's mbi did not match"
                log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)
            assert user.crosswalk.user_mbi_hash == mbi_hash, "Found user's mbi did not match"
        else:
            # Previously stored value was None/Null, so update just the mbi hash.
            mesg = "UPDATE mbi_hash since previous value was NULL"
            log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)
            user.crosswalk.user_mbi_hash = mbi_hash
            user.crosswalk.save()

        # Update hash type used for lookup, if it has changed from last match.
        if user.crosswalk.user_id_type != hash_lookup_type:
            mesg = "UPDATE user_id_type as it has changed from the previous lookup value"
            log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)
            user.crosswalk.user_id_type = hash_lookup_type
            user.crosswalk.save()

        mesg = "RETURN existing beneficiary record"
        log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)
        return user
    except User.DoesNotExist:
        pass

    first_name = user_info.get('given_name', "")
    last_name = user_info.get('family_name', "")
    email = user_info.get('email', "")

    user = create_beneficiary_record(username=subject,
                                     user_hicn_hash=hicn_hash,
                                     user_mbi_hash=mbi_hash,
                                     fhir_id=fhir_id,
                                     first_name=first_name,
                                     last_name=last_name,
                                     email=email,
                                     user_id_type=hash_lookup_type)

    mesg = "CREATE beneficiary record"
    log_get_and_update_user(user, fhir_id, mbi_hash, hicn_hash, hash_lookup_type, mesg)
    return user


# TODO default empty strings to null, requires non-null constraints to be fixed
def create_beneficiary_record(username=None,
                              user_hicn_hash=None,
                              user_mbi_hash=None,
                              fhir_id=None,
                              first_name="",
                              last_name="",
                              email="",
                              user_id_type="H"):

    # Pre logging for asserts.
    if username is None:
        mesg = "username can not be None"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)

    if username == "":
        mesg = "username can not be an empty string"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)

    if user_hicn_hash is None:
        mesg = "user_hicn_hash can not be None"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)
    else:
        if len(user_hicn_hash) != 64:
            mesg = "incorrect user HICN hash format"
            log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)

    if user_mbi_hash is not None:
        if len(user_mbi_hash) != 64:
            mesg = "incorrect user MBI hash format"
            log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)

    if fhir_id is None:
        mesg = "fhir_id can not be None"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)

    if fhir_id == "":
        mesg = "fhir_id can not be an empty string"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)

    assert username is not None
    assert username != ""
    assert user_hicn_hash is not None
    assert len(user_hicn_hash) == 64, "incorrect user HICN hash format"
    # If mbi_hash is not NULL, perform length check.
    if user_mbi_hash is not None:
        assert len(user_mbi_hash) == 64, "incorrect user MBI hash format"
    assert fhir_id is not None
    assert fhir_id != ""

    if User.objects.filter(username=username).exists():
        mesg = "user already exists"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)
        raise ValidationError(mesg, username)

    if Crosswalk.objects.filter(_user_id_hash=user_hicn_hash).exists():
        mesg = "user_hicn_hash already exists"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)
        raise ValidationError("user_hicn_hash already exists", user_hicn_hash)

    # If mbi_hash is not NULL, perform check for duplicate
    if user_mbi_hash is not None:
        if Crosswalk.objects.filter(_user_mbi_hash=user_mbi_hash).exists():
            mesg = "user_mbi_hash already exists"
            log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)
            raise ValidationError("user_mbi_hash already exists", user_hicn_hash)

    if fhir_id and Crosswalk.objects.filter(_fhir_id=fhir_id).exists():
        mesg = "fhir_id already exists"
        log_create_beneficiary_record(username, fhir_id, user_mbi_hash, user_hicn_hash, mesg)
        raise ValidationError("fhir_id already exists", fhir_id)

    with transaction.atomic():
        user = User(username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email)
        user.set_unusable_password()
        user.save()
        Crosswalk.objects.create(user=user,
                                 user_hicn_hash=user_hicn_hash,
                                 user_mbi_hash=user_mbi_hash,
                                 fhir_id=fhir_id,
                                 user_id_type=user_id_type)

        # Extra user information
        # TODO: remove the idea of UserProfile
        UserProfile.objects.create(user=user, user_type='BEN')
        # TODO: magic strings are bad
        group = Group.objects.get(name='BlueButton')  # TODO: these do not need a group
        user.groups.add(group)
    return user


class AnonUserState(models.Model):
    state = models.CharField(default='', max_length=64, db_index=True)
    next_uri = models.CharField(default='', max_length=512)

    def __str__(self):
        return '%s %s' % (self.state, self.next_uri)
