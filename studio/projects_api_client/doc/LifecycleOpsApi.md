# projects_api_client.api.LifecycleOpsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getProjectSettingsApiProjectsProjectNameSettingsGet**](LifecycleOpsApi.md#getprojectsettingsapiprojectsprojectnamesettingsget) | **GET** /api/projects/{project_name}/settings | Get Project Settings
[**recreateProjectServicesApiProjectsProjectNameRecreateServicesPost**](LifecycleOpsApi.md#recreateprojectservicesapiprojectsprojectnamerecreateservicespost) | **POST** /api/projects/{project_name}/recreate-services | Recreate Project Services
[**restartProjectApiProjectsProjectNameRestartPost**](LifecycleOpsApi.md#restartprojectapiprojectsprojectnamerestartpost) | **POST** /api/projects/{project_name}/restart | Restart Project
[**startProjectApiProjectsProjectNameStartPost**](LifecycleOpsApi.md#startprojectapiprojectsprojectnamestartpost) | **POST** /api/projects/{project_name}/start | Start Project
[**stopProjectApiProjectsProjectNameStopPost**](LifecycleOpsApi.md#stopprojectapiprojectsprojectnamestoppost) | **POST** /api/projects/{project_name}/stop | Stop Project
[**updateProjectSettingsApiProjectsProjectNameSettingsPut**](LifecycleOpsApi.md#updateprojectsettingsapiprojectsprojectnamesettingsput) | **PUT** /api/projects/{project_name}/settings | Update Project Settings


# **getProjectSettingsApiProjectsProjectNameSettingsGet**
> Object getProjectSettingsApiProjectsProjectNameSettingsGet(projectName)

Get Project Settings

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getProjectSettingsApiProjectsProjectNameSettingsGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->getProjectSettingsApiProjectsProjectNameSettingsGet: $e\n');
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

# **recreateProjectServicesApiProjectsProjectNameRecreateServicesPost**
> Object recreateProjectServicesApiProjectsProjectNameRecreateServicesPost(projectName, recreateServices)

Recreate Project Services

Recreate specific services of a project using docker compose down + up. This is needed (instead of just restart) because env vars are read at container creation time, not on restart.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectName = projectName_example; // String | 
final recreateServices = RecreateServices(); // RecreateServices | 

try {
    final result = api_instance.recreateProjectServicesApiProjectsProjectNameRecreateServicesPost(projectName, recreateServices);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->recreateProjectServicesApiProjectsProjectNameRecreateServicesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **recreateServices** | [**RecreateServices**](RecreateServices.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **restartProjectApiProjectsProjectNameRestartPost**
> Object restartProjectApiProjectsProjectNameRestartPost(projectName)

Restart Project

Reinicia os containers do projeto. Enfileirado por projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.restartProjectApiProjectsProjectNameRestartPost(projectName);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->restartProjectApiProjectsProjectNameRestartPost: $e\n');
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

# **startProjectApiProjectsProjectNameStartPost**
> Object startProjectApiProjectsProjectNameStartPost(projectName)

Start Project

Inicia os containers do projeto. Enfileirado por projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.startProjectApiProjectsProjectNameStartPost(projectName);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->startProjectApiProjectsProjectNameStartPost: $e\n');
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

# **stopProjectApiProjectsProjectNameStopPost**
> Object stopProjectApiProjectsProjectNameStopPost(projectName)

Stop Project

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.stopProjectApiProjectsProjectNameStopPost(projectName);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->stopProjectApiProjectsProjectNameStopPost: $e\n');
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

# **updateProjectSettingsApiProjectsProjectNameSettingsPut**
> Object updateProjectSettingsApiProjectsProjectNameSettingsPut(projectName, updateSettings)

Update Project Settings

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectName = projectName_example; // String | 
final updateSettings = UpdateSettings(); // UpdateSettings | 

try {
    final result = api_instance.updateProjectSettingsApiProjectsProjectNameSettingsPut(projectName, updateSettings);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->updateProjectSettingsApiProjectsProjectNameSettingsPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **updateSettings** | [**UpdateSettings**](UpdateSettings.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

