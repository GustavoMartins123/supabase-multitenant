#!/bin/bash
jq -r 'to_entries[] | .value.Certificates[] | "\(.domain.main) \(.certificate)"' acme.json | while read -r domain cert_base64; do
  echo "🔐 Domínio: $domain"
  echo "$cert_base64" | base64 -d | openssl x509 -noout -dates | grep 'notAfter'
  echo "-------------------------------"
done
