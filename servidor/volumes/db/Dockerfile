FROM busybox:1.38.0-musl AS tools
FROM supabase/postgres:17.12.0.001
COPY --from=tools /bin/busybox /usr/local/bin/less
COPY pg_hba.conf /etc/postgresql/pg_hba.conf
COPY configure-pg-hba.sh /usr/local/bin/configure-pg-hba.sh
COPY entrypoint-hba.sh /usr/local/bin/entrypoint-hba.sh
RUN chmod +x /usr/local/bin/less /usr/local/bin/configure-pg-hba.sh /usr/local/bin/entrypoint-hba.sh \
    && chown postgres:postgres /etc/postgresql/pg_hba.conf \
    && chmod 0640 /etc/postgresql/pg_hba.conf
ENTRYPOINT ["/usr/local/bin/entrypoint-hba.sh"]
CMD ["postgres"]