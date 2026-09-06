# projects_api_client.api.LifecycleApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getContainerLogsApiProjectsProjectNameLogsServiceGet**](LifecycleApi.md#getcontainerlogsapiprojectsprojectnamelogsserviceget) | **GET** /api/projects/{project_name}/logs/{service} | Get Container Logs
[**getProjectDockerStatusApiProjectsProjectNameStatusGet**](LifecycleApi.md#getprojectdockerstatusapiprojectsprojectnamestatusget) | **GET** /api/projects/{project_name}/status | Get Project Docker Status


# **getContainerLogsApiProjectsProjectNameLogsServiceGet**
> ContainerLogsResponse getContainerLogsApiProjectsProjectNameLogsServiceGet(projectName, service, lines)

Get Container Logs

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleApi();
final projectName = projectName_example; // String | 
final service = service_example; // String | 
final lines = 56; // int | 

try {
    final result = api_instance.getContainerLogsApiProjectsProjectNameLogsServiceGet(projectName, service, lines);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleApi->getContainerLogsApiProjectsProjectNameLogsServiceGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **service** | **String**|  | 
 **lines** | **int**|  | [optional] [default to 100]

### Return type

[**ContainerLogsResponse**](ContainerLogsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectDockerStatusApiProjectsProjectNameStatusGet**
> ProjectStatusResponse getProjectDockerStatusApiProjectsProjectNameStatusGet(projectName)

Get Project Docker Status

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getProjectDockerStatusApiProjectsProjectNameStatusGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleApi->getProjectDockerStatusApiProjectsProjectNameStatusGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**ProjectStatusResponse**](ProjectStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

