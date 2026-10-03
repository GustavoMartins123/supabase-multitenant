# projects_api_client.api.LifecycleApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getContainerLogsApiProjectsProjectRefLogsServiceGet**](LifecycleApi.md#getcontainerlogsapiprojectsprojectreflogsserviceget) | **GET** /api/projects/{project_ref}/logs/{service} | Get Container Logs
[**getProjectDockerStatusApiProjectsProjectRefStatusGet**](LifecycleApi.md#getprojectdockerstatusapiprojectsprojectrefstatusget) | **GET** /api/projects/{project_ref}/status | Get Project Docker Status


# **getContainerLogsApiProjectsProjectRefLogsServiceGet**
> ContainerLogsResponse getContainerLogsApiProjectsProjectRefLogsServiceGet(projectRef, service, lines)

Get Container Logs

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleApi();
final projectRef = projectRef_example; // String |
final service = service_example; // String | 
final lines = 56; // int | 

try {
    final result = api_instance.getContainerLogsApiProjectsProjectRefLogsServiceGet(projectRef, service, lines);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleApi->getContainerLogsApiProjectsProjectRefLogsServiceGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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

# **getProjectDockerStatusApiProjectsProjectRefStatusGet**
> ProjectStatusResponse getProjectDockerStatusApiProjectsProjectRefStatusGet(projectRef)

Get Project Docker Status

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getProjectDockerStatusApiProjectsProjectRefStatusGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleApi->getProjectDockerStatusApiProjectsProjectRefStatusGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**ProjectStatusResponse**](ProjectStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

