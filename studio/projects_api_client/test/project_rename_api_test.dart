//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

import 'package:projects_api_client/api.dart';
import 'package:test/test.dart';


/// tests for ProjectRenameApi
void main() {
  // final instance = ProjectRenameApi();

  group('tests for ProjectRenameApi', () {
    // Get Project Config Token
    //
    // Entrega o token compartilhado aos membros do projeto e registra a leitura.
    //
    //Future<Object> getProjectConfigTokenApiProjectsProjectNameConfigTokenGet(String projectName) async
    test('test getProjectConfigTokenApiProjectsProjectNameConfigTokenGet', () async {
      // TODO
    });

    // Get Project Queue Status
    //
    // Retorna o estado atual da fila de ações do projeto.  Inclui o job em execução (se houver), o tamanho da fila, e os jobs pendentes/rodando do banco para fins de UI (polling).
    //
    //Future<Object> getProjectQueueStatusApiProjectsProjectNameQueueStatusGet(String projectName) async
    test('test getProjectQueueStatusApiProjectsProjectNameQueueStatusGet', () async {
      // TODO
    });

    // Get Project Rename History
    //
    // Retorna auditoria e historico duravel de nome/path do projeto.
    //
    //Future<Object> getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet(String projectName, { int limit }) async
    test('test getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet', () async {
      // TODO
    });

    // Rename Project
    //
    // Renomeia o slug/path do projeto (migração completa em background).  O escopo inclui: nome interno na meta DB, banco Postgres, roles por projeto, replication slots do Realtime, tenant Supavisor, diretório físico e templates (nginx, docker-compose, .env).
    //
    //Future<Object> renameProjectApiProjectsProjectNameRenamePost(String projectName, ProjectRenameRequest projectRenameRequest) async
    test('test renameProjectApiProjectsProjectNameRenamePost', () async {
      // TODO
    });

    // Update Project Display Name
    //
    // Atualiza apenas o display_name do projeto (sem migrar infraestrutura).
    //
    //Future<Object> updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch(String projectName, ProjectDisplayNameUpdate projectDisplayNameUpdate) async
    test('test updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch', () async {
      // TODO
    });

  });
}
