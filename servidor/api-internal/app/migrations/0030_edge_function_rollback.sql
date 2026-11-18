ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN (
        'save_draft', 'publish', 'configure', 'unpublish', 'delete',
        'set_secret', 'delete_secret', 'configure_function', 'test_invoke', 'rollback'
    ));
