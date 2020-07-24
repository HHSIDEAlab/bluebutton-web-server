from rest_framework import exceptions
from requests.exceptions import HTTPError
from apps.fhir.bluebutton.exceptions import UpstreamServerException
from apps.test import BaseApiTest
from httmock import HTTMock, urlmatch
from ..authentication import match_backend_patient_identifier
from .responses import responses


class TestAuthentication(BaseApiTest):

    MOCK_FHIR_URL = "fhir.backend.bluebutton.hhsdevcloud.us"
    MOCK_FHIR_PATH = "/v1/fhir/Patient/"
    MOCK_FHIR_HICN_QUERY = ".*hicnHash.*"
    MOCK_FHIR_MBI_QUERY = ".*mbi-hash.*"

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_HICN_QUERY)
    def fhir_match_hicn_success_mock(self, url, request):
        return responses['success']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_HICN_QUERY)
    def fhir_match_hicn_not_found_mock(self, url, request):
        return responses['not_found']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_HICN_QUERY)
    def fhir_match_hicn_error_mock(self, url, request):
        return responses['error']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_HICN_QUERY)
    def fhir_match_hicn_duplicates_mock(self, url, request):
        return responses['duplicates']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_HICN_QUERY)
    def fhir_match_hicn_malformed_mock(self, url, request):
        return responses['malformed']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_HICN_QUERY)
    def fhir_match_hicn_lying_mock(self, url, request):
        return responses['lying']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_MBI_QUERY)
    def fhir_match_mbi_success_mock(self, url, request):
        return responses['success']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_MBI_QUERY)
    def fhir_match_mbi_not_found_mock(self, url, request):
        return responses['not_found']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_MBI_QUERY)
    def fhir_match_mbi_error_mock(self, url, request):
        return responses['error']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_MBI_QUERY)
    def fhir_match_mbi_duplicates_mock(self, url, request):
        return responses['duplicates']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_MBI_QUERY)
    def fhir_match_mbi_malformed_mock(self, url, request):
        return responses['malformed']

    @urlmatch(netloc=MOCK_FHIR_URL, path=MOCK_FHIR_PATH, query=MOCK_FHIR_MBI_QUERY)
    def fhir_match_mbi_lying_mock(self, url, request):
        return responses['lying']

    def test_match_backend_patient_identifier_success(self):
        '''
            Testing responses: HICN = success
                               MBI = success
            Expecting: Match via MBI first / hash_lockup_type="M"
        '''
        with HTTMock(self.fhir_match_hicn_success_mock, self.fhir_match_mbi_success_mock):
            fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                mbi_hash=self.test_mbi_hash,
                hicn_hash=self.test_hicn_hash)
            self.assertEqual(backend_data, responses['success']['content'])
            self.assertEqual(fhir_id, "-20000000002346")
            self.assertEqual(hash_lookup_type, "M")

    def test_match_backend_patient_identifier_hicn_success(self):
        '''
            Testing responses: HICN = success
                               MBI = not_found
            Expecting: Match via HICN / hash_lockup_type="H"
        '''
        with HTTMock(self.fhir_match_hicn_success_mock, self.fhir_match_mbi_not_found_mock):
            fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                mbi_hash=self.test_mbi_hash,
                hicn_hash=self.test_hicn_hash)
            self.assertEqual(backend_data, responses['success']['content'])
            self.assertEqual(fhir_id, "-20000000002346")
            self.assertEqual(hash_lookup_type, "H")

    def test_match_backend_patient_identifier_mbi_success(self):
        '''
            Testing responses: HICN = not_found
                               MBI = success
            Expecting: Match via MBI / hash_lockup_type="M"
        '''
        with HTTMock(self.fhir_match_hicn_not_found_mock, self.fhir_match_mbi_success_mock):
            fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                mbi_hash=self.test_mbi_hash,
                hicn_hash=self.test_hicn_hash)
            self.assertEqual(backend_data, responses['success']['content'])
            self.assertEqual(fhir_id, "-20000000002346")
            self.assertEqual(hash_lookup_type, "M")

    def test_match_backend_patient_identifier_not_found(self):
        '''
            Testing responses: HICN = not_found
                               MBI = not_found
            Expecting: NotFound exception raised
        '''
        with HTTMock(self.fhir_match_hicn_not_found_mock, self.fhir_match_mbi_not_found_mock):
            with self.assertRaises(exceptions.NotFound):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_server_hicn_error(self):
        '''
            Testing responses: HICN = error
                               MBI = not_found
            Expecting: HTTPError exception raised
        '''
        with HTTMock(self.fhir_match_hicn_error_mock, self.fhir_match_mbi_not_found_mock):
            with self.assertRaises(HTTPError):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_server_mbi_error(self):
        '''
            Testing responses: HICN = not_found
                               MBI = error
            Expecting: HTTPError exception raised
        '''
        with HTTMock(self.fhir_match_hicn_not_found_mock, self.fhir_match_mbi_error_mock):
            with self.assertRaises(HTTPError):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_duplicates_hicn(self):
        '''
            Testing responses: HICN = duplicates
                               MBI = not_found
            Expecting: UpstreamServerException exception raised
        '''
        with HTTMock(self.fhir_match_hicn_duplicates_mock, self.fhir_match_mbi_not_found_mock):
            with self.assertRaisesRegexp(UpstreamServerException, "^Duplicate.*total"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_duplicates_mbi(self):
        '''
            Testing responses: HICN = success
                               MBI = duplicates
            Expecting: UpstreamServerException exception raised
        '''
        with HTTMock(self.fhir_match_hicn_success_mock, self.fhir_match_mbi_duplicates_mock):
            with self.assertRaisesRegexp(UpstreamServerException, "^Duplicate.*"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_duplicates_both(self):
        '''
            Testing responses: HICN = duplicates
                               MBI = duplicates
            Expecting: UpstreamServerException exception raised
        '''
        with HTTMock(self.fhir_match_hicn_duplicates_mock, self.fhir_match_mbi_duplicates_mock):
            with self.assertRaisesRegexp(UpstreamServerException, "^Duplicate.*"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_malformed_hicn(self):
        '''
            Testing responses: HICN = malformed
                               MBI = not_found
            Expecting: KeyError exception raised
        '''
        with HTTMock(self.fhir_match_hicn_malformed_mock, self.fhir_match_mbi_not_found_mock):
            with self.assertRaisesRegexp(KeyError, "id"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_malformed_mbi(self):
        '''
            Testing responses: HICN = success
                               MBI = malformed
            Expecting: KeyError exception raised
        '''
        with HTTMock(self.fhir_match_hicn_success_mock, self.fhir_match_mbi_malformed_mock):
            with self.assertRaisesRegexp(KeyError, "id"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_lying_hicn(self):
        '''
            Testing responses: HICN = lying
                               MBI = not_found
            Expecting: UpstreamServerException exception raised
            Note: lying means response total=1, but there are multiple
                  Patient resources in the response.
        '''
        with HTTMock(self.fhir_match_hicn_lying_mock, self.fhir_match_mbi_not_found_mock):
            with self.assertRaisesRegexp(UpstreamServerException, "^Duplicate.*bundle entry"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)

    def test_match_backend_patient_identifier_lying_mbi(self):
        '''
            Testing responses: HICN = success
                               MBI = lying
            Expecting: UpstreamServerException exception raised
            Note: lying means response total=1, but there are multiple
                  Patient resources in the response.
        '''
        with HTTMock(self.fhir_match_hicn_success_mock, self.fhir_match_mbi_lying_mock):
            with self.assertRaisesRegexp(UpstreamServerException, "^Duplicate.*bundle entry"):
                fhir_id, backend_data, hash_lookup_type = match_backend_patient_identifier(
                    mbi_hash=self.test_mbi_hash,
                    hicn_hash=self.test_hicn_hash)
