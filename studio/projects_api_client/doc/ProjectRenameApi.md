# projects_api_client.api.ProjectRenameApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getProjectConfigTokenApiProjectsProjectNameConfigTokenGet**](ProjectRenameApi.md#getprojectconfigtokenapiprojectsprojectnameconfigtokenget) | **GET** /api/projects/{project_name}/config-token | Get Project Config Token
[**getProjectQueueStatusApiProjectsProjectNameQueueStatusGet**](ProjectRenameApi.md#getprojectqueuestatusapiprojectsprojectnamequeuestatusget) | **GET** /api/projects/{project_name}/queue-status | Get Project Queue Status
[**getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet**](ProjectRenameApi.md#getprojectrenamehistoryapiprojectsprojectnamerenamehistoryget) | **GET** /api/projects/{project_name}/rename-history | Get Project Rename History
[**renameProjectApiProjectsProjectNameRenamePost**](ProjectRenameApi.md#renameprojectapiprojectsprojectnamerenamepost) | **POST** /api/projects/{project_name}/rename | Rename Project
[**updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch**](ProjectRenameApi.md#updateprojectdisplaynameapiprojectsprojectnamedisplaynamepatch) | **PATCH** /api/projects/{project_name}/display-name | Update Project Display Name


# **getProjectConfigTokenApiProjectsProjectNameConfigTokenGet**
> Object getProjectConfigTokenApiProjectsProjectNameConfigTokenGet(projectName)

Get Project Config Token

Entrega o token compartilhado aos membros do projeto e registra a leitura.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getProjectConfigTokenApiProjectsProjectNameConfigTokenGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->getProjectConfigTokenApiProjectsProjectNameConfigTokenGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectQueueStatusApiProjectsProjectNameQueueStatusGet**
> Object getProjectQueueStatusApiProjectsProjectNameQueueStatusGet(projectName)

Get Project Queue Status

Retorna o estado atual da fila de ações do projeto.  Inclui o job em execução (se houver), o tamanho da fila, e os jobs pendentes/rodando do banco para fins de UI (polling).

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getProjectQueueStatusApiProjectsProjectNameQueueStatusGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->getProjectQueueStatusApiProjectsProjectNameQueueStatusGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet**
> Object getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet(projectName, limit)

Get Project Rename History

Retorna auditoria e historico duravel de nome/path do projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectName = projectName_example; // String | 
final limit = 56; // int | 

try {
    final result = api_instance.getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet(projectName, limit);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **limit** | **int**|  | [optional] [default to 50]

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **renameProjectApiProjectsProjectNameRenamePost**
> Object renameProjectApiProjectsProjectNameRenamePost(projectName, projectRenameRequest)

Rename Project

Renomeia o slug/path do projeto (migração completa em background).  O escopo inclui: nome interno na meta DB, banco Postgres, roles por projeto, replication slots do Realtime, tenant Supavisor, diretório físico e templates (nginx, docker-compose, .env).

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectName = projectName_example; // String | 
final projectRenameRequest = ProjectRenameRequest(); // ProjectRenameRequest | 

try {
    final result = api_instance.renameProjectApiProjectsProjectNameRenamePost(projectName, projectRenameRequest);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->renameProjectApiProjectsProjectNameRenamePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **projectRenameRequest** | [**ProjectRenameRequest**](ProjectRenameRequest.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch**
> Object updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch(projectName, projectDisplayNameUpdate)

Update Project Display Name

Atualiza apenas o display_name do projeto (sem migrar infraestrutura).

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectName = projectName_example; // String | 
final projectDisplayNameUpdate = ProjectDisplayNameUpdate(); // ProjectDisplayNameUpdate | 

try {
    final result = api_instance.updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch(projectName, projectDisplayNameUpdate);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **projectDisplayNameUpdate** | [**ProjectDisplayNameUpdate**](ProjectDisplayNameUpdate.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

