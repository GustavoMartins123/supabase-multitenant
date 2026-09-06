# projects_api_client.api.ProjectKeysApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**rotateProjectKeyApiProjectsProjectNameRotateKeyPost**](ProjectKeysApi.md#rotateprojectkeyapiprojectsprojectnamerotatekeypost) | **POST** /api/projects/{project_name}/rotate-key | Rotate Project Key
[**updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPut**](ProjectKeysApi.md#updateautomatickeyrotationapiprojectsprojectnameautomatickeyrotationput) | **PUT** /api/projects/{project_name}/automatic-key-rotation | Update Automatic Key Rotation


# **rotateProjectKeyApiProjectsProjectNameRotateKeyPost**
> RotateProjectKeyResponse rotateProjectKeyApiProjectsProjectNameRotateKeyPost(projectName)

Rotate Project Key

Rotaciona anon/service_role via script. Enfileirado por projeto.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.rotateProjectKeyApiProjectsProjectNameRotateKeyPost(projectName);
    print(result);
} catch (e) {
    print('Exception when calling ProjectKeysApi->rotateProjectKeyApiProjectsProjectNameRotateKeyPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 

### Return type

[**RotateProjectKeyResponse**](RotateProjectKeyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPut**
> AutomaticKeyRotationResponse updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPut(projectName, automaticKeyRotationUpdate)

Update Automatic Key Rotation

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ProjectKeysApi();
final projectName = projectName_example; // String | 
final automaticKeyRotationUpdate = AutomaticKeyRotationUpdate(); // AutomaticKeyRotationUpdate | 

try {
    final result = api_instance.updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPut(projectName, automaticKeyRotationUpdate);
    print(result);
} catch (e) {
    print('Exception when calling ProjectKeysApi->updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **automaticKeyRotationUpdate** | [**AutomaticKeyRotationUpdate**](AutomaticKeyRotationUpdate.md)|  | 

### Return type

[**AutomaticKeyRotationResponse**](AutomaticKeyRotationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

