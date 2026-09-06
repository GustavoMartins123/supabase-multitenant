# projects_api_client.api.InternalApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**encKeyApiProjectsInternalEncKeyRefGet**](InternalApi.md#enckeyapiprojectsinternalenckeyrefget) | **GET** /api/projects/internal/enc-key/{ref} | Enc Key
[**getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGet**](InternalApi.md#getcontentprojectidentityapiprojectsinternalcontentidentityprojectnameget) | **GET** /api/projects/internal/content-identity/{project_name} | Get Content Project Identity
[**getStudioProjectContextApiProjectsInternalStudioContextRefGet**](InternalApi.md#getstudioprojectcontextapiprojectsinternalstudiocontextrefget) | **GET** /api/projects/internal/studio-context/{ref} | Get Studio Project Context
[**projectKeyVersionApiProjectsInternalKeyVersionRefGet**](InternalApi.md#projectkeyversionapiprojectsinternalkeyversionrefget) | **GET** /api/projects/internal/key-version/{ref} | Project Key Version
[**proxyGlobalAnalyticsDelete**](InternalApi.md#proxyglobalanalyticsdelete) | **DELETE** /api/internal/analytics/{analytics_path} | Proxy Global Analytics
[**proxyGlobalAnalyticsGet**](InternalApi.md#proxyglobalanalyticsget) | **GET** /api/internal/analytics/{analytics_path} | Proxy Global Analytics
[**proxyGlobalAnalyticsPost**](InternalApi.md#proxyglobalanalyticspost) | **POST** /api/internal/analytics/{analytics_path} | Proxy Global Analytics
[**proxyGlobalAnalyticsPut**](InternalApi.md#proxyglobalanalyticsput) | **PUT** /api/internal/analytics/{analytics_path} | Proxy Global Analytics
[**syncUserIdentityApiProjectsInternalUsersSyncPost**](InternalApi.md#syncuseridentityapiprojectsinternaluserssyncpost) | **POST** /api/projects/internal/users/sync | Sync User Identity


# **encKeyApiProjectsInternalEncKeyRefGet**
> Object encKeyApiProjectsInternalEncKeyRefGet(ref)

Enc Key

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final ref = ref_example; // String | 

try {
    final result = api_instance.encKeyApiProjectsInternalEncKeyRefGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->encKeyApiProjectsInternalEncKeyRefGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGet**
> Object getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGet(projectName)

Get Content Project Identity

Resolve o slug mutável para o UUID estável usado apenas por content.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGet: $e\n');
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

# **getStudioProjectContextApiProjectsInternalStudioContextRefGet**
> Object getStudioProjectContextApiProjectsInternalStudioContextRefGet(ref)

Get Studio Project Context

Resolve and authorize the project carried by the Studio URL.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final ref = ref_example; // String | 

try {
    final result = api_instance.getStudioProjectContextApiProjectsInternalStudioContextRefGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->getStudioProjectContextApiProjectsInternalStudioContextRefGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **projectKeyVersionApiProjectsInternalKeyVersionRefGet**
> Object projectKeyVersionApiProjectsInternalKeyVersionRefGet(ref)

Project Key Version

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final ref = ref_example; // String | 

try {
    final result = api_instance.projectKeyVersionApiProjectsInternalKeyVersionRefGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->projectKeyVersionApiProjectsInternalKeyVersionRefGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyGlobalAnalyticsDelete**
> Object proxyGlobalAnalyticsDelete(analyticsPath)

Proxy Global Analytics

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final analyticsPath = analyticsPath_example; // String | 

try {
    final result = api_instance.proxyGlobalAnalyticsDelete(analyticsPath);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->proxyGlobalAnalyticsDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **analyticsPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyGlobalAnalyticsGet**
> Object proxyGlobalAnalyticsGet(analyticsPath)

Proxy Global Analytics

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final analyticsPath = analyticsPath_example; // String | 

try {
    final result = api_instance.proxyGlobalAnalyticsGet(analyticsPath);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->proxyGlobalAnalyticsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **analyticsPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyGlobalAnalyticsPost**
> Object proxyGlobalAnalyticsPost(analyticsPath)

Proxy Global Analytics

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final analyticsPath = analyticsPath_example; // String | 

try {
    final result = api_instance.proxyGlobalAnalyticsPost(analyticsPath);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->proxyGlobalAnalyticsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **analyticsPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyGlobalAnalyticsPut**
> Object proxyGlobalAnalyticsPut(analyticsPath)

Proxy Global Analytics

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final analyticsPath = analyticsPath_example; // String | 

try {
    final result = api_instance.proxyGlobalAnalyticsPut(analyticsPath);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->proxyGlobalAnalyticsPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **analyticsPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **syncUserIdentityApiProjectsInternalUsersSyncPost**
> Object syncUserIdentityApiProjectsInternalUsersSyncPost(userSyncPayload)

Sync User Identity

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = InternalApi();
final userSyncPayload = UserSyncPayload(); // UserSyncPayload | 

try {
    final result = api_instance.syncUserIdentityApiProjectsInternalUsersSyncPost(userSyncPayload);
    print(result);
} catch (e) {
    print('Exception when calling InternalApi->syncUserIdentityApiProjectsInternalUsersSyncPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **userSyncPayload** | [**UserSyncPayload**](UserSyncPayload.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

