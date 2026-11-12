#!/usr/bin/env bash
# Bancos internos do cluster compartilhado. O banco de um projeto e
# "_supabase_<nome>", entao um nome como "storage" ou "template" apontaria
# para um banco da plataforma; nenhum fluxo de projeto pode remove-los,
# renomea-los ou sobrescreve-los.

PROTECTED_DATABASES=(postgres template0 template1 _supabase _supabase_storage _supabase_template meta_trap)

protected_database_assert_droppable() {
  local db="${1:-}" protected
  [[ -n "$db" ]] || { echo "Nome de banco vazio recusado" >&2; return 1; }
  for protected in "${PROTECTED_DATABASES[@]}"; do
    if [[ "$db" == "$protected" ]]; then
      echo "Banco interno da plataforma protegido: $db" >&2
      return 1
    fi
  done
  [[ "$db" == _supabase_* ]] || {
    echo "Banco fora do namespace de projetos recusado: $db" >&2
    return 1
  }
}
