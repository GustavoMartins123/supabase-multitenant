# projects_api_client.api.RestorePointsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**createProjectRestorePointApiProjectsProjectNameRestorePointsPost**](RestorePointsApi.md#createprojectrestorepointapiprojectsprojectnamerestorepointspost) | **POST** /api/projects/{project_name}/restore-points | Create Project Restore Point
[**deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDelete**](RestorePointsApi.md#deleteprojectrestorepointapiprojectsprojectnamerestorepointspointiddelete) | **DELETE** /api/projects/{project_name}/restore-points/{point_id} | Delete Project Restore Point
[**listProjectRestorePointsApiProjectsProjectNameRestorePointsGet**](RestorePointsApi.md#listprojectrestorepointsapiprojectsprojectnamerestorepointsget) | **GET** /api/projects/{project_name}/restore-points | List Project Restore Points
[**restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePost**](RestorePointsApi.md#restoreprojectrestorepointapiprojectsprojectnamerestorepointspointidrestorepost) | **POST** /api/projects/{project_name}/restore-points/{point_id}/restore | Restore Project Restore Point


# **createProjectRestorePointApiProjectsProjectNameRestorePointsPost**
> CreateRestorePointResponse createProjectRestorePointApiProjectsProjectNameRestorePointsPost(projectName, restorePointCreate)

Create Project Restore Point

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectName = projectName_example; // String | 
final restorePointCreate = RestorePointCreate(); // RestorePointCreate | 

try {
    final result = api_instance.createProjectRestorePointApiProjectsProjectNameRestorePointsPost(projectName, restorePointCreate);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->createProjectRestorePointApiProjectsProjectNameRestorePointsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **restorePointCreate** | [**RestorePointCreate**](RestorePointCreate.md)|  | 

### Return type

[**CreateRestorePointResponse**](CreateRestorePointResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDelete**
> DeleteRestorePointResponse deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDelete(projectName, pointId)

Delete Project Restore Point

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectName = projectName_example; // String | 
final pointId = pointId_example; // String | 

try {
    final result = api_instance.deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDelete(projectName, pointId);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **pointId** | **String**|  | 

### Return type

[**DeleteRestorePointResponse**](DeleteRestorePointResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listProjectRestorePointsApiProjectsProjectNameRestorePointsGet**
> ListRestorePointsResponse listProjectRestorePointsApiProjectsProjectNameRestorePointsGet(projectName)

List Project Restore Points

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.listProjectRestorePointsApiProjectsProjectNameRestorePointsGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->listProjectRestorePointsApiProjectsProjectNameRestorePointsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**ListRestorePointsResponse**](ListRestorePointsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePost**
> RestoreRestorePointResponse restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePost(projectName, pointId)

Restore Project Restore Point

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = RestorePointsApi();
final projectName = projectName_example; // String | 
final pointId = pointId_example; // String | 

try {
    final result = api_instance.restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePost(projectName, pointId);
    print(result);
} catch (e) {
    print('Exception when calling RestorePointsApi->restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **pointId** | **String**|  | 

### Return type

[**RestoreRestorePointResponse**](RestoreRestorePointResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

