FROM busybox:1.38.0-musl AS tools
FROM supabase/postgres:17.11.0.003
COPY --from=tools /bin/busybox /usr/local/bin/less
RUN chmod +x /usr/local/bin/less