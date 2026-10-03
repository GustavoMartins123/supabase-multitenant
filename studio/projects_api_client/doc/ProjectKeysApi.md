# projects_api_client.api.ProjectKeysApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**rotateProjectKeyApiProjectsProjectRefRotateKeyPost**](ProjectKeysApi.md#rotateprojectkeyapiprojectsprojectrefrotatekeypost) | **POST** /api/projects/{project_ref}/rotate-key | Rotate Project Key
[**updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPut**](ProjectKeysApi.md#updateautomatickeyrotationapiprojectsprojectrefautomatickeyrotationput) | **PUT** /api/projects/{project_ref}/automatic-key-rotation | Update Automatic Key Rotation


# **rotateProjectKeyApiProjectsProjectRefRotateKeyPost**
> RotateProjectKeyResponse rotateProjectKeyApiProjectsProjectRefRotateKeyPost(projectRef)

Rotate Project Key

Rotaciona anon/service_role via script. Enfileirado por projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.rotateProjectKeyApiProjectsProjectRefRotateKeyPost(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling ProjectKeysApi->rotateProjectKeyApiProjectsProjectRefRotateKeyPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**RotateProjectKeyResponse**](RotateProjectKeyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPut**
> AutomaticKeyRotationResponse updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPut(projectRef, automaticKeyRotationUpdate)

Update Automatic Key Rotation

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectKeysApi();
final projectRef = projectRef_example; // String |
final automaticKeyRotationUpdate = AutomaticKeyRotationUpdate(); // AutomaticKeyRotationUpdate | 

try {
    final result = api_instance.updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPut(projectRef, automaticKeyRotationUpdate);
    print(result);
} catch (e) {
    print('Exception when calling ProjectKeysApi->updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **automaticKeyRotationUpdate** | [**AutomaticKeyRotationUpdate**](AutomaticKeyRotationUpdate.md)|  | 

### Return type

[**AutomaticKeyRotationResponse**](AutomaticKeyRotationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

