# projects_api_client.api.ProjectsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**createProjectApiProjectsPost**](ProjectsApi.md#createprojectapiprojectspost) | **POST** /api/projects | Create Project
[**deleteProjectApiProjectsProjectNameDelete**](ProjectsApi.md#deleteprojectapiprojectsprojectnamedelete) | **DELETE** /api/projects/{project_name} | Delete Project
[**duplicateProjectApiProjectsDuplicatePost**](ProjectsApi.md#duplicateprojectapiprojectsduplicatepost) | **POST** /api/projects/duplicate | Duplicate Project
[**listProjectsApiProjectsGet**](ProjectsApi.md#listprojectsapiprojectsget) | **GET** /api/projects | List Projects


# **createProjectApiProjectsPost**
> Object createProjectApiProjectsPost(newProject)

Create Project

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectsApi();
final newProject = NewProject(); // NewProject | 

try {
    final result = api_instance.createProjectApiProjectsPost(newProject);
    print(result);
} catch (e) {
    print('Exception when calling ProjectsApi->createProjectApiProjectsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **newProject** | [**NewProject**](NewProject.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deleteProjectApiProjectsProjectNameDelete**
> Object deleteProjectApiProjectsProjectNameDelete(projectName, xStepUpToken)

Delete Project

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectsApi();
final projectName = projectName_example; // String | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.deleteProjectApiProjectsProjectNameDelete(projectName, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling ProjectsApi->deleteProjectApiProjectsProjectNameDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **duplicateProjectApiProjectsDuplicatePost**
> Object duplicateProjectApiProjectsDuplicatePost(duplicateProject)

Duplicate Project

Duplica um projeto existente. - Valida acesso do usuário ao projeto original - Cria registro no banco - Dispara job em background para executar script de duplicação

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectsApi();
final duplicateProject = DuplicateProject(); // DuplicateProject | 

try {
    final result = api_instance.duplicateProjectApiProjectsDuplicatePost(duplicateProject);
    print(result);
} catch (e) {
    print('Exception when calling ProjectsApi->duplicateProjectApiProjectsDuplicatePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **duplicateProject** | [**DuplicateProject**](DuplicateProject.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listProjectsApiProjectsGet**
> Object listProjectsApiProjectsGet()

List Projects

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectsApi();

try {
    final result = api_instance.listProjectsApiProjectsGet();
    print(result);
} catch (e) {
    print('Exception when calling ProjectsApi->listProjectsApiProjectsGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

