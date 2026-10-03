#!/bin/sh
set -eu
printf 'users: {}\n' > /config/users_database.yml
printf 0 > /config/.studio-directory-sequence
chown 65534:65534 /config /config/users_database.yml /config/.studio-directory-sequence
chmod 777 /config
chmod 666 /config/users_database.yml /config/.studio-directory-sequence
exec openresty -c /workspace/tests/integration/fixtures/studio_directory.nginx.conf
