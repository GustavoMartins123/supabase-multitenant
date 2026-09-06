# projects_api_client.api.JobsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**listJobHistoryApiJobsGet**](JobsApi.md#listjobhistoryapijobsget) | **GET** /api/jobs | List Job History
[**projectStatusApiProjectsStatusJobIdGet**](JobsApi.md#projectstatusapiprojectsstatusjobidget) | **GET** /api/projects/status/{job_id} | Project Status
[**retryProjectJobApiJobsJobIdRetryPost**](JobsApi.md#retryprojectjobapijobsjobidretrypost) | **POST** /api/jobs/{job_id}/retry | Retry Project Job


# **listJobHistoryApiJobsGet**
> JobListResponse listJobHistoryApiJobsGet(projectUuid, action, status, limit, offset)

List Job History

Lista o historico duravel de jobs visivel para o usuario autenticado.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = JobsApi();
final projectUuid = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final action = action_example; // String | 
final status = status_example; // String | 
final limit = 56; // int | 
final offset = 56; // int | 

try {
    final result = api_instance.listJobHistoryApiJobsGet(projectUuid, action, status, limit, offset);
    print(result);
} catch (e) {
    print('Exception when calling JobsApi->listJobHistoryApiJobsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectUuid** | **String**|  | [optional] 
 **action** | **String**|  | [optional] 
 **status** | **String**|  | [optional] 
 **limit** | **int**|  | [optional] [default to 50]
 **offset** | **int**|  | [optional] [default to 0]

### Return type

[**JobListResponse**](JobListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **projectStatusApiProjectsStatusJobIdGet**
> JobResponse projectStatusApiProjectsStatusJobIdGet(jobId)

Project Status

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = JobsApi();
final jobId = jobId_example; // String | 

try {
    final result = api_instance.projectStatusApiProjectsStatusJobIdGet(jobId);
    print(result);
} catch (e) {
    print('Exception when calling JobsApi->projectStatusApiProjectsStatusJobIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**JobResponse**](JobResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **retryProjectJobApiJobsJobIdRetryPost**
> JobRetryResponse retryProjectJobApiJobsJobIdRetryPost(jobId)

Retry Project Job

Cria uma nova tentativa apenas para acoes explicitamente idempotentes.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = JobsApi();
final jobId = jobId_example; // String | 

try {
    final result = api_instance.retryProjectJobApiJobsJobIdRetryPost(jobId);
    print(result);
} catch (e) {
    print('Exception when calling JobsApi->retryProjectJobApiJobsJobIdRetryPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**JobRetryResponse**](JobRetryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

