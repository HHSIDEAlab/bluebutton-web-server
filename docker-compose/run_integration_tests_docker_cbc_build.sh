#!/bin/bash

# This script performs setup to run the tests in our bb2-cbc-build docker image container.
# It is used by our CBC Jenkins and local development testing.

# Echo function that includes script name on each line for console log readability
echo_msg () {
  echo "$(basename $0): $*"
}

# main
#set -e
echo_msg "Running script: $0"
echo_msg
echo_msg "  Using ENV/environment variables:"
echo_msg
echo_msg "                    BRANCH:  ${BRANCH}"
echo_msg 
echo_msg "                  FHIR_URL:  ${FHIR_URL}"
echo_msg
echo_msg "     DJANGO_FHIR_CERTSTORE: ${DJANGO_FHIR_CERTSTORE}"
echo_msg
echo_msg "                 CERT_FILE: ${CERT_FILE}"
echo_msg "                  KEY_FILE: ${KEY_FILE}"
echo_msg
echo_msg "            FHIR_CERT_FILE: ${FHIR_CERT_FILE}"
echo_msg "             FHIR_KEY_FILE: ${FHIR_KEY_FILE}"
echo_msg

# Clone from local repo if /app mount directory is found.
if [ -d /app ]
then
  echo_msg
  echo_msg "- Cloning webserver repo from LOCAL mounted /app to code."
  echo_msg
  git clone  /app code
  cd code
  echo_msg
fi

## Checkout commit hash or branch if set
#if [ "${BRANCH}" != "" ]
#then
#  echo_msg
#  echo_msg "- Checkout commit hash or branch from: BRANCH = ${BRANCH}"
#  git fetch origin "+refs/heads/master:refs/remotes/origin/master" "+refs/pull/*:refs/remotes/origin/pr/*"
#  git checkout "${BRANCH}"
#else
#  echo_msg
#  echo_msg "- Using currently checked out branch in local development."
#fi

# Show git status.
echo_msg
echo_msg "- GIT STATUS:"
git status

echo_msg
echo_msg "- GET Python version info:"
python --version

# Setup Python virtual env.
echo_msg
echo_msg "- Setup Python virtual env:"
python3 -m venv venv
. venv/bin/activate

# Install requirements.
echo_msg
echo_msg "- Install PIP requirements:"
pip install -r requirements/requirements.txt --no-index --find-links ./vendor/
pip install sqlparse

# Run integration tests script.
echo_msg
echo_msg "- Running integration tests in StaticLiveServerTestCase mode:"
echo_msg
sh docker-compose/run_integration_tests.sh
result_status=$?

# Return status.
echo_msg
echo_msg
echo_msg "RETURNED: result_status: ${result_status}"
echo_msg
exit ${result_status}
