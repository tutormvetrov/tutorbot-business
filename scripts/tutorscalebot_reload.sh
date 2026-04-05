#!/usr/bin/env bash
set -euo pipefail

rm -f /srv/tutorscalebot/.restart-trigger
/usr/bin/systemctl restart tutorscalebot.service
