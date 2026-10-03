# projects_api_client.api.LifecycleOpsApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getProjectSettingsApiProjectsProjectRefSettingsGet**](LifecycleOpsApi.md#getprojectsettingsapiprojectsprojectrefsettingsget) | **GET** /api/projects/{project_ref}/settings | Get Project Settings
[**recreateProjectServicesApiProjectsProjectRefRecreateServicesPost**](LifecycleOpsApi.md#recreateprojectservicesapiprojectsprojectrefrecreateservicespost) | **POST** /api/projects/{project_ref}/recreate-services | Recreate Project Services
[**restartProjectApiProjectsProjectRefRestartPost**](LifecycleOpsApi.md#restartprojectapiprojectsprojectrefrestartpost) | **POST** /api/projects/{project_ref}/restart | Restart Project
[**startProjectApiProjectsProjectRefStartPost**](LifecycleOpsApi.md#startprojectapiprojectsprojectrefstartpost) | **POST** /api/projects/{project_ref}/start | Start Project
[**stopProjectApiProjectsProjectRefStopPost**](LifecycleOpsApi.md#stopprojectapiprojectsprojectrefstoppost) | **POST** /api/projects/{project_ref}/stop | Stop Project
[**updateProjectSettingsApiProjectsProjectRefSettingsPut**](LifecycleOpsApi.md#updateprojectsettingsapiprojectsprojectrefsettingsput) | **PUT** /api/projects/{project_ref}/settings | Update Project Settings


# **getProjectSettingsApiProjectsProjectRefSettingsGet**
> GetProjectSettingsResponse getProjectSettingsApiProjectsProjectRefSettingsGet(projectRef)

Get Project Settings

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getProjectSettingsApiProjectsProjectRefSettingsGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->getProjectSettingsApiProjectsProjectRefSettingsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**GetProjectSettingsResponse**](GetProjectSettingsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **recreateProjectServicesApiProjectsProjectRefRecreateServicesPost**
> RecreateProjectServicesResponse recreateProjectServicesApiProjectsProjectRefRecreateServicesPost(projectRef, recreateServices)

Recreate Project Services

Recreate specific services of a project using docker compose down + up. This is needed (instead of just restart) because env vars are read at container creation time, not on restart.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectRef = projectRef_example; // String |
final recreateServices = RecreateServices(); // RecreateServices | 

try {
    final result = api_instance.recreateProjectServicesApiProjectsProjectRefRecreateServicesPost(projectRef, recreateServices);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->recreateProjectServicesApiProjectsProjectRefRecreateServicesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **recreateServices** | [**RecreateServices**](RecreateServices.md)|  | 

### Return type

[**RecreateProjectServicesResponse**](RecreateProjectServicesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **restartProjectApiProjectsProjectRefRestartPost**
> RestartProjectResponse restartProjectApiProjectsProjectRefRestartPost(projectRef)

Restart Project

Reinicia os containers do projeto. Enfileirado por projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.restartProjectApiProjectsProjectRefRestartPost(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->restartProjectApiProjectsProjectRefRestartPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**RestartProjectResponse**](RestartProjectResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **startProjectApiProjectsProjectRefStartPost**
> StartProjectResponse startProjectApiProjectsProjectRefStartPost(projectRef)

Start Project

Inicia os containers do projeto. Enfileirado por projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.startProjectApiProjectsProjectRefStartPost(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->startProjectApiProjectsProjectRefStartPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**StartProjectResponse**](StartProjectResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **stopProjectApiProjectsProjectRefStopPost**
> StopProjectResponse stopProjectApiProjectsProjectRefStopPost(projectRef)

Stop Project

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.stopProjectApiProjectsProjectRefStopPost(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->stopProjectApiProjectsProjectRefStopPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**StopProjectResponse**](StopProjectResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectSettingsApiProjectsProjectRefSettingsPut**
> UpdateProjectSettingsResponse updateProjectSettingsApiProjectsProjectRefSettingsPut(projectRef, updateSettings)

Update Project Settings

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = LifecycleOpsApi();
final projectRef = projectRef_example; // String |
final updateSettings = UpdateSettings(); // UpdateSettings | 

try {
    final result = api_instance.updateProjectSettingsApiProjectsProjectRefSettingsPut(projectRef, updateSettings);
    print(result);
} catch (e) {
    print('Exception when calling LifecycleOpsApi->updateProjectSettingsApiProjectsProjectRefSettingsPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **updateSettings** | [**UpdateSettings**](UpdateSettings.md)|  | 

### Return type

[**UpdateProjectSettingsResponse**](UpdateProjectSettingsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

