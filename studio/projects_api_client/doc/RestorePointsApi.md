# projects_api_client.api.RestorePointsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**createProjectRestorePointApiProjectsProjectRefRestorePointsPost**](RestorePointsApi.md#createprojectrestorepointapiprojectsprojectrefrestorepointspost) | **POST** /api/projects/{project_ref}/restore-points | Create Project Restore Point
[**deleteProjectRestorePointApiProjectsProjectRefRestorePointsPointIdDelete**](RestorePointsApi.md#deleteprojectrestorepointapiprojectsprojectrefrestorepointspointiddelete) | **DELETE** /api/projects/{project_ref}/restore-points/{point_id} | Delete Project Restore Point
[**listProjectRestorePointsApiProjectsProjectRefRestorePointsGet**](RestorePointsApi.md#listprojectrestorepointsapiprojectsprojectrefrestorepointsget) | **GET** /api/projects/{project_ref}/restore-points | List Project Restore Points
[**restoreProjectRestorePointApiProjectsProjectRefRestorePointsPointIdRestorePost**](RestorePointsApi.md#restoreprojectrestorepointapiprojectsprojectrefrestorepointspointidrestorepost) | **POST** /api/projects/{project_ref}/restore-points/{point_id}/restore | Restore Project Restore Point


# **createProjectRestorePointApiProjectsProjectRefRestorePointsPost**
> CreateRestorePointResponse createProjectRestorePointApiProjectsProjectRefRestorePointsPost(projectRef, restorePointCreate)

Create Project Restore Point

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectRef = projectRef_example; // String |
final restorePointCreate = RestorePointCreate(); // RestorePointCreate | 

try {
    final result = api_instance.createProjectRestorePointApiProjectsProjectRefRestorePointsPost(projectRef, restorePointCreate);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->createProjectRestorePointApiProjectsProjectRefRestorePointsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **restorePointCreate** | [**RestorePointCreate**](RestorePointCreate.md)|  | 

### Return type

[**CreateRestorePointResponse**](CreateRestorePointResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deleteProjectRestorePointApiProjectsProjectRefRestorePointsPointIdDelete**
> DeleteRestorePointResponse deleteProjectRestorePointApiProjectsProjectRefRestorePointsPointIdDelete(projectRef, pointId)

Delete Project Restore Point

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectRef = projectRef_example; // String |
final pointId = pointId_example; // String | 

try {
    final result = api_instance.deleteProjectRestorePointApiProjectsProjectRefRestorePointsPointIdDelete(projectRef, pointId);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->deleteProjectRestorePointApiProjectsProjectRefRestorePointsPointIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **pointId** | **String**|  | 

### Return type

[**DeleteRestorePointResponse**](DeleteRestorePointResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listProjectRestorePointsApiProjectsProjectRefRestorePointsGet**
> ListRestorePointsResponse listProjectRestorePointsApiProjectsProjectRefRestorePointsGet(projectRef)

List Project Restore Points

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.listProjectRestorePointsApiProjectsProjectRefRestorePointsGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->listProjectRestorePointsApiProjectsProjectRefRestorePointsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**ListRestorePointsResponse**](ListRestorePointsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **restoreProjectRestorePointApiProjectsProjectRefRestorePointsPointIdRestorePost**
> RestoreRestorePointResponse restoreProjectRestorePointApiProjectsProjectRefRestorePointsPointIdRestorePost(projectRef, pointId)

Restore Project Restore Point

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectRef = projectRef_example; // String |
final pointId = pointId_example; // String | 

try {
    final result = api_instance.restoreProjectRestorePointApiProjectsProjectRefRestorePointsPointIdRestorePost(projectRef, pointId);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->restoreProjectRestorePointApiProjectsProjectRefRestorePointsPointIdRestorePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **pointId** | **String**|  | 

### Return type

[**RestoreRestorePointResponse**](RestoreRestorePointResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

