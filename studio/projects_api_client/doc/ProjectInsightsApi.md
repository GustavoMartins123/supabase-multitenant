# projects_api_client.api.ProjectInsightsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**executeProjectFunctionApiProjectsRefExecuteFunctionPost**](ProjectInsightsApi.md#executeprojectfunctionapiprojectsrefexecutefunctionpost) | **POST** /api/projects/{ref}/execute-function | Execute Project Function
[**getProjectAiFunctionsApiProjectsRefFunctionsGet**](ProjectInsightsApi.md#getprojectaifunctionsapiprojectsreffunctionsget) | **GET** /api/projects/{ref}/functions | Get Project Ai Functions
[**getProjectS3VectorKeysApiProjectsProjectNameStorageS3KeysGet**](ProjectInsightsApi.md#getprojects3vectorkeysapiprojectsprojectnamestorages3keysget) | **GET** /api/projects/{project_name}/storage/s3-keys | Get Project S3 Vector Keys
[**getProjectUserTelemetryApiProjectsProjectNameTelemetryUsersGet**](ProjectInsightsApi.md#getprojectusertelemetryapiprojectsprojectnametelemetryusersget) | **GET** /api/projects/{project_name}/telemetry/users | Get Project User Telemetry
[**getProjectsForUserApiAdminProjectsInfoPost**](ProjectInsightsApi.md#getprojectsforuserapiadminprojectsinfopost) | **POST** /api/admin/projects-info | Get Projects For User
[**listAllUsersForAdminApiAdminProjectsNameAllUsersGet**](ProjectInsightsApi.md#listallusersforadminapiadminprojectsnameallusersget) | **GET** /api/admin/projects/{name}/all-users | List All Users For Admin
[**proxyProjectMetaDelete**](ProjectInsightsApi.md#proxyprojectmetadelete) | **DELETE** /api/projects/{ref}/meta | Proxy Project Meta
[**proxyProjectMetaGet**](ProjectInsightsApi.md#proxyprojectmetaget) | **GET** /api/projects/{ref}/meta | Proxy Project Meta
[**proxyProjectMetaPatch**](ProjectInsightsApi.md#proxyprojectmetapatch) | **PATCH** /api/projects/{ref}/meta | Proxy Project Meta
[**proxyProjectMetaPathDelete**](ProjectInsightsApi.md#proxyprojectmetapathdelete) | **DELETE** /api/projects/{ref}/meta/{meta_path} | Proxy Project Meta
[**proxyProjectMetaPathGet**](ProjectInsightsApi.md#proxyprojectmetapathget) | **GET** /api/projects/{ref}/meta/{meta_path} | Proxy Project Meta
[**proxyProjectMetaPathPatch**](ProjectInsightsApi.md#proxyprojectmetapathpatch) | **PATCH** /api/projects/{ref}/meta/{meta_path} | Proxy Project Meta
[**proxyProjectMetaPathPost**](ProjectInsightsApi.md#proxyprojectmetapathpost) | **POST** /api/projects/{ref}/meta/{meta_path} | Proxy Project Meta
[**proxyProjectMetaPost**](ProjectInsightsApi.md#proxyprojectmetapost) | **POST** /api/projects/{ref}/meta | Proxy Project Meta
[**transferProjectApiProjectsProjectNameTransferPost**](ProjectInsightsApi.md#transferprojectapiprojectsprojectnametransferpost) | **POST** /api/projects/{project_name}/transfer | Transfer Project


# **executeProjectFunctionApiProjectsRefExecuteFunctionPost**
> List<Map<String, Object>> executeProjectFunctionApiProjectsRefExecuteFunctionPost(ref, requestBody)

Execute Project Function

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final requestBody = Map<String, Object>(); // Map<String, Object> | 

try {
    final result = api_instance.executeProjectFunctionApiProjectsRefExecuteFunctionPost(ref, requestBody);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->executeProjectFunctionApiProjectsRefExecuteFunctionPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **requestBody** | [**Map<String, Object>**](Object.md)|  | 

### Return type

[**List<Map<String, Object>>**](Map.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectAiFunctionsApiProjectsRefFunctionsGet**
> List<ProjectAIFunctionItem> getProjectAiFunctionsApiProjectsRefFunctionsGet(ref)

Get Project Ai Functions

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 

try {
    final result = api_instance.getProjectAiFunctionsApiProjectsRefFunctionsGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->getProjectAiFunctionsApiProjectsRefFunctionsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 

### Return type

[**List<ProjectAIFunctionItem>**](ProjectAIFunctionItem.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectS3VectorKeysApiProjectsProjectNameStorageS3KeysGet**
> ProjectS3VectorKeysResponse getProjectS3VectorKeysApiProjectsProjectNameStorageS3KeysGet(projectName)

Get Project S3 Vector Keys

Return the selected tenant's SigV4 pair to an authorized Studio admin.  OpenResty rewrites the Studio's fixed ``/api/get-s3-keys`` endpoint to this project-scoped route. The service HMAC authenticates the Studio-to-control- plane hop and the signed user token is checked here.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getProjectS3VectorKeysApiProjectsProjectNameStorageS3KeysGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->getProjectS3VectorKeysApiProjectsProjectNameStorageS3KeysGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**ProjectS3VectorKeysResponse**](ProjectS3VectorKeysResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectUserTelemetryApiProjectsProjectNameTelemetryUsersGet**
> ProjectUserTelemetryResponse getProjectUserTelemetryApiProjectsProjectNameTelemetryUsersGet(projectName, period, start, end)

Get Project User Telemetry

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final projectName = projectName_example; // String | 
final period = period_example; // String | 
final start = 2013-10-20T19:20:30+01:00; // DateTime | 
final end = 2013-10-20T19:20:30+01:00; // DateTime | 

try {
    final result = api_instance.getProjectUserTelemetryApiProjectsProjectNameTelemetryUsersGet(projectName, period, start, end);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->getProjectUserTelemetryApiProjectsProjectNameTelemetryUsersGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **period** | **String**|  | [optional] [default to '24h']
 **start** | **DateTime**|  | [optional] 
 **end** | **DateTime**|  | [optional] 

### Return type

[**ProjectUserTelemetryResponse**](ProjectUserTelemetryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProjectsForUserApiAdminProjectsInfoPost**
> ProjectsInfoResponse getProjectsForUserApiAdminProjectsInfoPost(requestBody)

Get Projects For User

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final requestBody = Map<String, String>(); // Map<String, String> | 

try {
    final result = api_instance.getProjectsForUserApiAdminProjectsInfoPost(requestBody);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->getProjectsForUserApiAdminProjectsInfoPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **requestBody** | [**Map<String, String>**](String.md)|  | 

### Return type

[**ProjectsInfoResponse**](ProjectsInfoResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listAllUsersForAdminApiAdminProjectsNameAllUsersGet**
> AllUsersResponse listAllUsersForAdminApiAdminProjectsNameAllUsersGet(name)

List All Users For Admin

Lista todos os usuários disponíveis para admins. Como a API não tem acesso ao cache, retorna uma estrutura que o Nginx pode completar ou usa proxy para Nginx.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final name = name_example; // String | 

try {
    final result = api_instance.listAllUsersForAdminApiAdminProjectsNameAllUsersGet(name);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->listAllUsersForAdminApiAdminProjectsNameAllUsersGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **String**|  | 

### Return type

[**AllUsersResponse**](AllUsersResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaDelete**
> Object proxyProjectMetaDelete(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaDelete(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | [optional] [default to '']

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaGet**
> Object proxyProjectMetaGet(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaGet(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | [optional] [default to '']

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaPatch**
> Object proxyProjectMetaPatch(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaPatch(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | [optional] [default to '']

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaPathDelete**
> Object proxyProjectMetaPathDelete(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaPathDelete(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaPathDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaPathGet**
> Object proxyProjectMetaPathGet(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaPathGet(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaPathGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaPathPatch**
> Object proxyProjectMetaPathPatch(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaPathPatch(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaPathPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaPathPost**
> Object proxyProjectMetaPathPost(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaPathPost(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaPathPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **proxyProjectMetaPost**
> Object proxyProjectMetaPost(ref, metaPath)

Proxy Project Meta

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final ref = ref_example; // String | 
final metaPath = metaPath_example; // String | 

try {
    final result = api_instance.proxyProjectMetaPost(ref, metaPath);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->proxyProjectMetaPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  | 
 **metaPath** | **String**|  | [optional] [default to '']

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **transferProjectApiProjectsProjectNameTransferPost**
> TransferResponse transferProjectApiProjectsProjectNameTransferPost(projectName, transferBody)

Transfer Project

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectInsightsApi();
final projectName = projectName_example; // String | 
final transferBody = TransferBody(); // TransferBody | 

try {
    final result = api_instance.transferProjectApiProjectsProjectNameTransferPost(projectName, transferBody);
    print(result);
} catch (e) {
    print('Exception when calling ProjectInsightsApi->transferProjectApiProjectsProjectNameTransferPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **transferBody** | [**TransferBody**](TransferBody.md)|  | 

### Return type

[**TransferResponse**](TransferResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

