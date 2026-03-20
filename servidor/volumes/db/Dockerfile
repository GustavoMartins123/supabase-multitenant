FROM busybox:1.37.0-musl AS tools
FROM supabase/postgres:15.14.1.098
COPY --from=tools /bin/busybox /usr/local/bin/less
RUN chmod +x /usr/local/bin/less