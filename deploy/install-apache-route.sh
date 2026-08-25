#!/usr/bin/env bash
set -euo pipefail

vhost=/etc/apache2/sites-available/000-default-le-ssl.conf
route_marker='ProxyPass        /dashboard/'

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

if grep -Fq "${route_marker}" "${vhost}"; then
  echo "The /dashboard/ proxy route is already installed."
  apache2ctl configtest
  systemctl reload apache2
  exit 0
fi

backup="${vhost}.before-dashboard-$(date -u +%Y%m%dT%H%M%SZ)"
cp --preserve=all "${vhost}" "${backup}"

python3 - "${vhost}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
contents = path.read_text()
marker = "\tProxyAddHeaders On"
snippet = """        ProxyPass        /dashboard/ http://127.0.0.1:9528/
        ProxyPassReverse /dashboard/ http://127.0.0.1:9528/

        <Location /dashboard/>
            Require all granted
            ProxyPreserveHost On
        </Location>

"""

if marker not in contents:
    raise SystemExit(f"Insertion marker not found in {path}")
path.write_text(contents.replace(marker, snippet + marker, 1))
PY

if ! apache2ctl configtest; then
  cp --preserve=all "${backup}" "${vhost}"
  echo "Apache validation failed; restored ${backup}." >&2
  exit 1
fi

systemctl reload apache2
echo "Installed /dashboard/ -> 127.0.0.1:9528 and reloaded Apache."
echo "Backup: ${backup}"
