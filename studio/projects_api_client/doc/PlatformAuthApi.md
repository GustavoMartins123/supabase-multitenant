# projects_api_client.api.PlatformAuthApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGet**](PlatformAuthApi.md#listprojectauthusersapiprojectsinternalauthusersprojectnameget) | **GET** /api/projects/internal/auth-users/{project_name} | List Project Auth Users
[**proxyProjectAuthAdminDelete**](PlatformAuthApi.md#proxyprojectauthadmindelete) | **DELETE** /api/projects/internal/auth-admin/{project_name}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminGet**](PlatformAuthApi.md#proxyprojectauthadminget) | **GET** /api/projects/internal/auth-admin/{project_name}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminPatch**](PlatformAuthApi.md#proxyprojectauthadminpatch) | **PATCH** /api/projects/internal/auth-admin/{project_name}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminPost**](PlatformAuthApi.md#proxyprojectauthadminpost) | **POST** /api/projects/internal/auth-admin/{project_name}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminPut**](PlatformAuthApi.md#proxyprojectauthadminput) | **PUT** /api/projects/internal/auth-admin/{project_name}/{gotrue_path} | Proxy Project Auth Admin


# **listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGet**
> AuthUsersResponse listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGet(projectName, page, perPage)

List Project Auth Users

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectName = projectName_example; // String | 
final page = 56; // int | 
final perPage = 56; // int | 

try {
    final result = api_instance.listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGet(projectName, page, perPage);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **page** | **int**|  | [optional] [default to 1]
 **perPage** | **int**|  | [optional] [default to 50]

### Return type

[**AuthUsersResponse**](AuthUsersResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectAuthAdminDelete**
> Object proxyProjectAuthAdminDelete(projectName, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectName = projectName_example; // String | 
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminDelete(projectName, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **gotruePath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectAuthAdminGet**
> Object proxyProjectAuthAdminGet(projectName, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectName = projectName_example; // String | 
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminGet(projectName, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **gotruePath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectAuthAdminPatch**
> Object proxyProjectAuthAdminPatch(projectName, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectName = projectName_example; // String | 
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminPatch(projectName, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **gotruePath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectAuthAdminPost**
> Object proxyProjectAuthAdminPost(projectName, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectName = projectName_example; // String | 
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminPost(projectName, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **gotruePath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectAuthAdminPut**
> Object proxyProjectAuthAdminPut(projectName, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectName = projectName_example; // String | 
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminPut(projectName, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **gotruePath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

