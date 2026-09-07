-- 1) Alteracao de policy, cancelamento de rotacao e revogacao de uma
--    secret key passaram a exigir step-up, igual a criacao/rotacao/ativacao/
--    revelacao. O CHECK da tabela precisa aceitar as novas acoes, senao o
--    consumo do grant falha com violacao de constraint.
ALTER TABLE studio_step_up_grant_consumptions
    DROP CONSTRAINT IF EXISTS studio_step_up_grant_consumptions_action_check;

ALTER TABLE studio_step_up_grant_consumptions
    ADD CONSTRAINT studio_step_up_grant_consumptions_action_check
    CHECK (action IN (
        'delete_project',
        'reveal_secret_key',
        'create_secret_key',
        'rotate_secret_key',
        'activate_secret_key',
        'update_secret_key_policy',
        'cancel_secret_key_rotation',
        'revoke_secret_key'
    ));
