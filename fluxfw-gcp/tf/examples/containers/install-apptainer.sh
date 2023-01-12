#!/usr/env bash
#
APPTAINER_ASSETS=$(curl -s https://api.github.com/repos/apptainer/apptainer/releases/latest | jq '.[] | match(".*assets$"; "g") | .string' 2>/dev/null | tr -d '"')
APPTAINER_RPM=$(curl -s ${APPTAINER_ASSETS} | jq '.[] | .browser_download_url' | egrep .*apptainer-[[:digit:]].*x86_64 | tr -d '"')

dnf install -y ${APPTAINER_RPM}
