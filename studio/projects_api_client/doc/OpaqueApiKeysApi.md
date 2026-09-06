# projects_api_client.api.OpaqueApiKeysApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDelete**](OpaqueApiKeysApi.md#abortopaqueapikeymigrationapiprojectsprojectnameopaqueapikeysmigrationdelete) | **DELETE** /api/projects/{project_name}/opaque-api-keys/migration | Abort Opaque Api Key Migration
[**activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPost**](OpaqueApiKeysApi.md#activateapikeyslotapiprojectsprojectnameapikeyslotsslotidactivationpost) | **POST** /api/projects/{project_name}/api-key-slots/{slot_id}/activation | Activate Api Key Slot
[**cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDelete**](OpaqueApiKeysApi.md#cancelapikeyslotrotationapiprojectsprojectnameapikeyslotsslotidrotationdelete) | **DELETE** /api/projects/{project_name}/api-key-slots/{slot_id}/rotation | Cancel Api Key Slot Rotation
[**claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPost**](OpaqueApiKeysApi.md#claimapikeyapiprojectsprojectnameapikeyrevealskeyidclaimpost) | **POST** /api/projects/{project_name}/api-key-reveals/{key_id}/claim | Claim Api Key
[**confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPost**](OpaqueApiKeysApi.md#confirmapikeyslotinstallationapiprojectsprojectnameapikeyslotsslotidrotationconfirmationpost) | **POST** /api/projects/{project_name}/api-key-slots/{slot_id}/rotation-confirmation | Confirm Api Key Slot Installation
[**createApiKeySlotApiProjectsProjectNameApiKeySlotsPost**](OpaqueApiKeysApi.md#createapikeyslotapiprojectsprojectnameapikeyslotspost) | **POST** /api/projects/{project_name}/api-key-slots | Create Api Key Slot
[**cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPost**](OpaqueApiKeysApi.md#cutoveropaqueapikeymigrationapiprojectsprojectnameopaqueapikeysmigrationcutoverpost) | **POST** /api/projects/{project_name}/opaque-api-keys/migration/cutover | Cutover Opaque Api Key Migration
[**getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGet**](OpaqueApiKeysApi.md#getapikeyrevealsapiprojectsprojectnameapikeyrevealsget) | **GET** /api/projects/{project_name}/api-key-reveals | Get Api Key Reveals
[**getApiKeySlotsApiProjectsProjectNameApiKeySlotsGet**](OpaqueApiKeysApi.md#getapikeyslotsapiprojectsprojectnameapikeyslotsget) | **GET** /api/projects/{project_name}/api-key-slots | Get Api Key Slots
[**getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGet**](OpaqueApiKeysApi.md#getopaqueapikeymigrationapiprojectsprojectnameopaqueapikeysmigrationget) | **GET** /api/projects/{project_name}/opaque-api-keys/migration | Get Opaque Api Key Migration
[**prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePost**](OpaqueApiKeysApi.md#prepareopaqueapikeymigrationapiprojectsprojectnameopaqueapikeysmigrationpreparepost) | **POST** /api/projects/{project_name}/opaque-api-keys/migration/prepare | Prepare Opaque Api Key Migration
[**revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDelete**](OpaqueApiKeysApi.md#revokeapikeyslotapiprojectsprojectnameapikeyslotsslotiddelete) | **DELETE** /api/projects/{project_name}/api-key-slots/{slot_id} | Revoke Api Key Slot
[**rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPost**](OpaqueApiKeysApi.md#rotateapikeyslotapiprojectsprojectnameapikeyslotsslotidrotationpost) | **POST** /api/projects/{project_name}/api-key-slots/{slot_id}/rotation | Rotate Api Key Slot
[**updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatch**](OpaqueApiKeysApi.md#updateapikeyslotpolicyapiprojectsprojectnameapikeyslotsslotidpatch) | **PATCH** /api/projects/{project_name}/api-key-slots/{slot_id} | Update Api Key Slot Policy


# **abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDelete**
> Object abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDelete(projectName)

Abort Opaque Api Key Migration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDelete(projectName);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDelete: $e\n');
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

# **activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPost**
> Object activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPost(projectName, slotId, xStepUpToken)

Activate Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPost(projectName, slotId, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **slotId** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDelete**
> Object cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDelete(projectName, slotId)

Cancel Api Key Slot Rotation

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 

try {
    final result = api_instance.cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDelete(projectName, slotId);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **slotId** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPost**
> Object claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPost(projectName, keyId, xStepUpToken)

Claim Api Key

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final keyId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPost(projectName, keyId, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **keyId** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPost**
> Object confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPost(projectName, slotId, confirmApiKeyInstallation)

Confirm Api Key Slot Installation

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final confirmApiKeyInstallation = ConfirmApiKeyInstallation(); // ConfirmApiKeyInstallation | 

try {
    final result = api_instance.confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPost(projectName, slotId, confirmApiKeyInstallation);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **slotId** | **String**|  | 
 **confirmApiKeyInstallation** | [**ConfirmApiKeyInstallation**](ConfirmApiKeyInstallation.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createApiKeySlotApiProjectsProjectNameApiKeySlotsPost**
> Object createApiKeySlotApiProjectsProjectNameApiKeySlotsPost(projectName, createApiKeySlot, xStepUpToken)

Create Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final createApiKeySlot = CreateApiKeySlot(); // CreateApiKeySlot | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.createApiKeySlotApiProjectsProjectNameApiKeySlotsPost(projectName, createApiKeySlot, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->createApiKeySlotApiProjectsProjectNameApiKeySlotsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **createApiKeySlot** | [**CreateApiKeySlot**](CreateApiKeySlot.md)|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPost**
> Object cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPost(projectName)

Cutover Opaque Api Key Migration

Stop legacy ingress, activate confirmed keys, and start opaque-only.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPost(projectName);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPost: $e\n');
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

# **getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGet**
> Object getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGet(projectName)

Get Api Key Reveals

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGet: $e\n');
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

# **getApiKeySlotsApiProjectsProjectNameApiKeySlotsGet**
> Object getApiKeySlotsApiProjectsProjectNameApiKeySlotsGet(projectName)

Get Api Key Slots

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getApiKeySlotsApiProjectsProjectNameApiKeySlotsGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->getApiKeySlotsApiProjectsProjectNameApiKeySlotsGet: $e\n');
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

# **getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGet**
> Object getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGet(projectName)

Get Opaque Api Key Migration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGet(projectName);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGet: $e\n');
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

# **prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePost**
> Object prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePost(projectName)

Prepare Opaque Api Key Migration

Prepare rejected opaque keys without changing the running gateway.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 

try {
    final result = api_instance.prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePost(projectName);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePost: $e\n');
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

# **revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDelete**
> Object revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDelete(projectName, slotId)

Revoke Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 

try {
    final result = api_instance.revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDelete(projectName, slotId);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **slotId** | **String**|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPost**
> Object rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPost(projectName, slotId, rotateApiKeySlot, xStepUpToken)

Rotate Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final rotateApiKeySlot = RotateApiKeySlot(); // RotateApiKeySlot | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPost(projectName, slotId, rotateApiKeySlot, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **slotId** | **String**|  | 
 **rotateApiKeySlot** | [**RotateApiKeySlot**](RotateApiKeySlot.md)|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatch**
> Object updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatch(projectName, slotId, updateApiKeySlotPolicy)

Update Api Key Slot Policy

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectName = projectName_example; // String | 
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final updateApiKeySlotPolicy = UpdateApiKeySlotPolicy(); // UpdateApiKeySlotPolicy | 

try {
    final result = api_instance.updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatch(projectName, slotId, updateApiKeySlotPolicy);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectName** | **String**|  | 
 **slotId** | **String**|  | 
 **updateApiKeySlotPolicy** | [**UpdateApiKeySlotPolicy**](UpdateApiKeySlotPolicy.md)|  | 

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

