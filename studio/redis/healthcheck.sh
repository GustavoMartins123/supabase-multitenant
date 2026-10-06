#!/bin/sh
set -eu
REDISCLI_AUTH=$(cat /run/secrets/REDIS_SESSION_PASSWORD)
export REDISCLI_AUTH
[ "$(redis-cli --no-auth-warning ping)" = PONG ]
