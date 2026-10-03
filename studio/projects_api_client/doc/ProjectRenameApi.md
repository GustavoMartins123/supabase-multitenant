# projects_api_client.api.ProjectRenameApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getProjectConfigTokenApiProjectsProjectRefConfigTokenGet**](ProjectRenameApi.md#getprojectconfigtokenapiprojectsprojectrefconfigtokenget) | **GET** /api/projects/{project_ref}/config-token | Get Project Config Token
[**getProjectQueueStatusApiProjectsProjectRefQueueStatusGet**](ProjectRenameApi.md#getprojectqueuestatusapiprojectsprojectrefqueuestatusget) | **GET** /api/projects/{project_ref}/queue-status | Get Project Queue Status
[**getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGet**](ProjectRenameApi.md#getprojectrenamehistoryapiprojectsprojectrefrenamehistoryget) | **GET** /api/projects/{project_ref}/rename-history | Get Project Rename History
[**renameProjectApiProjectsProjectRefRenamePost**](ProjectRenameApi.md#renameprojectapiprojectsprojectrefrenamepost) | **POST** /api/projects/{project_ref}/rename | Rename Project
[**updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatch**](ProjectRenameApi.md#updateprojectdisplaynameapiprojectsprojectrefdisplaynamepatch) | **PATCH** /api/projects/{project_ref}/display-name | Update Project Display Name


# **getProjectConfigTokenApiProjectsProjectRefConfigTokenGet**
> ProjectConfigTokenResponse getProjectConfigTokenApiProjectsProjectRefConfigTokenGet(projectRef)

Get Project Config Token

Entrega o token compartilhado aos membros do projeto e registra a leitura.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getProjectConfigTokenApiProjectsProjectRefConfigTokenGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->getProjectConfigTokenApiProjectsProjectRefConfigTokenGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**ProjectConfigTokenResponse**](ProjectConfigTokenResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectQueueStatusApiProjectsProjectRefQueueStatusGet**
> ProjectQueueStatusResponse getProjectQueueStatusApiProjectsProjectRefQueueStatusGet(projectRef)

Get Project Queue Status

Retorna o estado atual da fila de ações do projeto.  Inclui o job em execução (se houver), o tamanho da fila, e os jobs pendentes/rodando do banco para fins de UI (polling).

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getProjectQueueStatusApiProjectsProjectRefQueueStatusGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->getProjectQueueStatusApiProjectsProjectRefQueueStatusGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**ProjectQueueStatusResponse**](ProjectQueueStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGet**
> ProjectRenameHistoryResponse getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGet(projectRef, limit)

Get Project Rename History

Retorna auditoria e historico duravel da referencia publica.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectRef = projectRef_example; // String |
final limit = 56; // int | 

try {
    final result = api_instance.getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGet(projectRef, limit);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **limit** | **int**|  | [optional] [default to 50]

### Return type

[**ProjectRenameHistoryResponse**](ProjectRenameHistoryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **renameProjectApiProjectsProjectRefRenamePost**
> RenameProjectResponse renameProjectApiProjectsProjectRefRenamePost(projectRef, body)

Rename Project

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectRef = projectRef_example; // String |
final body = Object(); // Object |

try {
    final result = api_instance.renameProjectApiProjectsProjectRefRenamePost(projectRef, body);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->renameProjectApiProjectsProjectRefRenamePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **body** | **Object**|  |

### Return type

[**RenameProjectResponse**](RenameProjectResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatch**
> UpdateDisplayNameResponse updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatch(projectRef, projectDisplayNameUpdate)

Update Project Display Name

Atualiza apenas o display_name do projeto (sem migrar infraestrutura).

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectRenameApi();
final projectRef = projectRef_example; // String |
final projectDisplayNameUpdate = ProjectDisplayNameUpdate(); // ProjectDisplayNameUpdate | 

try {
    final result = api_instance.updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatch(projectRef, projectDisplayNameUpdate);
    print(result);
} catch (e) {
    print('Exception when calling ProjectRenameApi->updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **projectDisplayNameUpdate** | [**ProjectDisplayNameUpdate**](ProjectDisplayNameUpdate.md)|  | 

### Return type

[**UpdateDisplayNameResponse**](UpdateDisplayNameResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

