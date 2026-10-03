# projects_api_client.api.PlatformAuthApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**listProjectAuthUsersApiProjectsInternalAuthUsersProjectRefGet**](PlatformAuthApi.md#listprojectauthusersapiprojectsinternalauthusersprojectrefget) | **GET** /api/projects/internal/auth-users/{project_ref} | List Project Auth Users
[**proxyProjectAuthAdminDelete**](PlatformAuthApi.md#proxyprojectauthadmindelete) | **DELETE** /api/projects/internal/auth-admin/{project_ref}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminGet**](PlatformAuthApi.md#proxyprojectauthadminget) | **GET** /api/projects/internal/auth-admin/{project_ref}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminPatch**](PlatformAuthApi.md#proxyprojectauthadminpatch) | **PATCH** /api/projects/internal/auth-admin/{project_ref}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminPost**](PlatformAuthApi.md#proxyprojectauthadminpost) | **POST** /api/projects/internal/auth-admin/{project_ref}/{gotrue_path} | Proxy Project Auth Admin
[**proxyProjectAuthAdminPut**](PlatformAuthApi.md#proxyprojectauthadminput) | **PUT** /api/projects/internal/auth-admin/{project_ref}/{gotrue_path} | Proxy Project Auth Admin


# **listProjectAuthUsersApiProjectsInternalAuthUsersProjectRefGet**
> AuthUsersResponse listProjectAuthUsersApiProjectsInternalAuthUsersProjectRefGet(projectRef, page, perPage)

List Project Auth Users

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectRef = projectRef_example; // String |
final page = 56; // int | 
final perPage = 56; // int | 

try {
    final result = api_instance.listProjectAuthUsersApiProjectsInternalAuthUsersProjectRefGet(projectRef, page, perPage);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->listProjectAuthUsersApiProjectsInternalAuthUsersProjectRefGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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
> Object proxyProjectAuthAdminDelete(projectRef, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectRef = projectRef_example; // String |
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminDelete(projectRef, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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
> Object proxyProjectAuthAdminGet(projectRef, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectRef = projectRef_example; // String |
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminGet(projectRef, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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
> Object proxyProjectAuthAdminPatch(projectRef, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectRef = projectRef_example; // String |
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminPatch(projectRef, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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
> Object proxyProjectAuthAdminPost(projectRef, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectRef = projectRef_example; // String |
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminPost(projectRef, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
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
> Object proxyProjectAuthAdminPut(projectRef, gotruePath)

Proxy Project Auth Admin

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = PlatformAuthApi();
final projectRef = projectRef_example; // String |
final gotruePath = gotruePath_example; // String | 

try {
    final result = api_instance.proxyProjectAuthAdminPut(projectRef, gotruePath);
    print(result);
} catch (e) {
    print('Exception when calling PlatformAuthApi->proxyProjectAuthAdminPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **gotruePath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

