-- 1) A ativacao (cut-over) de uma secret key passou a exigir step-up, igual a
--    criacao/rotacao/revelacao. O CHECK da tabela precisa aceitar a nova acao,
--    senao o consumo do grant falha com violacao de constraint.
ALTER TABLE studio_step_up_grant_consumptions
    DROP CONSTRAINT IF EXISTS studio_step_up_grant_consumptions_action_check;

ALTER TABLE studio_step_up_grant_consumptions
    ADD CONSTRAINT studio_step_up_grant_consumptions_action_check
    CHECK (action IN (
        'delete_project',
        'reveal_secret_key',
        'create_secret_key',
        'rotate_secret_key',
        'activate_secret_key'
    ));

-- 2) Nonces do HMAC interno (studio-nginx -> Projects API). O cache anterior era
--    um OrderedDict por processo: com mais de um worker ou replica, e apos
--    qualquer restart, o mesmo nonce voltava a ser aceito dentro da janela de
--    skew. A PRIMARY KEY faz a reivindicacao ser atomica no banco que a API ja
--    usa, valendo para todos os workers e replicas.
CREATE TABLE IF NOT EXISTS internal_hmac_nonces (
    service TEXT NOT NULL
        CHECK (service ~ '^[a-z][a-z0-9-]{0,63}$'),
    nonce TEXT NOT NULL
        CHECK (nonce ~ '^[0-9a-f]{32,128}$'),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (service, nonce)
);

-- Usado pela limpeza oportunista das linhas ja expiradas.
CREATE INDEX IF NOT EXISTS idx_internal_hmac_nonces_expires_at
    ON internal_hmac_nonces(expires_at);
