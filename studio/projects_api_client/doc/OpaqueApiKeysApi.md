# projects_api_client.api.OpaqueApiKeysApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDelete**](OpaqueApiKeysApi.md#abortopaqueapikeymigrationapiprojectsprojectrefopaqueapikeysmigrationdelete) | **DELETE** /api/projects/{project_ref}/opaque-api-keys/migration | Abort Opaque Api Key Migration
[**activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPost**](OpaqueApiKeysApi.md#activateapikeyslotapiprojectsprojectrefapikeyslotsslotidactivationpost) | **POST** /api/projects/{project_ref}/api-key-slots/{slot_id}/activation | Activate Api Key Slot
[**cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDelete**](OpaqueApiKeysApi.md#cancelapikeyslotrotationapiprojectsprojectrefapikeyslotsslotidrotationdelete) | **DELETE** /api/projects/{project_ref}/api-key-slots/{slot_id}/rotation | Cancel Api Key Slot Rotation
[**claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPost**](OpaqueApiKeysApi.md#claimapikeyapiprojectsprojectrefapikeyrevealskeyidclaimpost) | **POST** /api/projects/{project_ref}/api-key-reveals/{key_id}/claim | Claim Api Key
[**confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPost**](OpaqueApiKeysApi.md#confirmapikeyslotinstallationapiprojectsprojectrefapikeyslotsslotidrotationconfirmationpost) | **POST** /api/projects/{project_ref}/api-key-slots/{slot_id}/rotation-confirmation | Confirm Api Key Slot Installation
[**createApiKeySlotApiProjectsProjectRefApiKeySlotsPost**](OpaqueApiKeysApi.md#createapikeyslotapiprojectsprojectrefapikeyslotspost) | **POST** /api/projects/{project_ref}/api-key-slots | Create Api Key Slot
[**cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPost**](OpaqueApiKeysApi.md#cutoveropaqueapikeymigrationapiprojectsprojectrefopaqueapikeysmigrationcutoverpost) | **POST** /api/projects/{project_ref}/opaque-api-keys/migration/cutover | Cutover Opaque Api Key Migration
[**getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGet**](OpaqueApiKeysApi.md#getapikeyrevealsapiprojectsprojectrefapikeyrevealsget) | **GET** /api/projects/{project_ref}/api-key-reveals | Get Api Key Reveals
[**getApiKeySlotsApiProjectsProjectRefApiKeySlotsGet**](OpaqueApiKeysApi.md#getapikeyslotsapiprojectsprojectrefapikeyslotsget) | **GET** /api/projects/{project_ref}/api-key-slots | Get Api Key Slots
[**getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGet**](OpaqueApiKeysApi.md#getopaqueapikeymigrationapiprojectsprojectrefopaqueapikeysmigrationget) | **GET** /api/projects/{project_ref}/opaque-api-keys/migration | Get Opaque Api Key Migration
[**prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePost**](OpaqueApiKeysApi.md#prepareopaqueapikeymigrationapiprojectsprojectrefopaqueapikeysmigrationpreparepost) | **POST** /api/projects/{project_ref}/opaque-api-keys/migration/prepare | Prepare Opaque Api Key Migration
[**revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDelete**](OpaqueApiKeysApi.md#revokeapikeyslotapiprojectsprojectrefapikeyslotsslotiddelete) | **DELETE** /api/projects/{project_ref}/api-key-slots/{slot_id} | Revoke Api Key Slot
[**rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPost**](OpaqueApiKeysApi.md#rotateapikeyslotapiprojectsprojectrefapikeyslotsslotidrotationpost) | **POST** /api/projects/{project_ref}/api-key-slots/{slot_id}/rotation | Rotate Api Key Slot
[**updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatch**](OpaqueApiKeysApi.md#updateapikeyslotpolicyapiprojectsprojectrefapikeyslotsslotidpatch) | **PATCH** /api/projects/{project_ref}/api-key-slots/{slot_id} | Update Api Key Slot Policy


# **abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDelete**
> MigrationAbortResponse abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDelete(projectRef)

Abort Opaque Api Key Migration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDelete(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**MigrationAbortResponse**](MigrationAbortResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPost**
> SlotActivationResponse activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPost(projectRef, slotId, xStepUpToken)

Activate Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPost(projectRef, slotId, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**SlotActivationResponse**](SlotActivationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDelete**
> SlotCancelResponse cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDelete(projectRef, slotId, xStepUpToken)

Cancel Api Key Slot Rotation

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final xStepUpToken = xStepUpToken_example; // String |

try {
    final result = api_instance.cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDelete(projectRef, slotId, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional]

### Return type

[**SlotCancelResponse**](SlotCancelResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPost**
> RevealClaimResponse claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPost(projectRef, keyId, xStepUpToken)

Claim Api Key

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final keyId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPost(projectRef, keyId, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **keyId** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**RevealClaimResponse**](RevealClaimResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPost**
> SlotConfirmResponse confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPost(projectRef, slotId, confirmApiKeyInstallation)

Confirm Api Key Slot Installation

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final confirmApiKeyInstallation = ConfirmApiKeyInstallation(); // ConfirmApiKeyInstallation | 

try {
    final result = api_instance.confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPost(projectRef, slotId, confirmApiKeyInstallation);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  | 
 **confirmApiKeyInstallation** | [**ConfirmApiKeyInstallation**](ConfirmApiKeyInstallation.md)|  | 

### Return type

[**SlotConfirmResponse**](SlotConfirmResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createApiKeySlotApiProjectsProjectRefApiKeySlotsPost**
> IssuedKeyResponse createApiKeySlotApiProjectsProjectRefApiKeySlotsPost(projectRef, createApiKeySlot, xStepUpToken)

Create Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final createApiKeySlot = CreateApiKeySlot(); // CreateApiKeySlot | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.createApiKeySlotApiProjectsProjectRefApiKeySlotsPost(projectRef, createApiKeySlot, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->createApiKeySlotApiProjectsProjectRefApiKeySlotsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **createApiKeySlot** | [**CreateApiKeySlot**](CreateApiKeySlot.md)|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**IssuedKeyResponse**](IssuedKeyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPost**
> MigrationCutoverResponse cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPost(projectRef)

Cutover Opaque Api Key Migration

Stop legacy ingress, activate confirmed keys, and start opaque-only.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPost(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**MigrationCutoverResponse**](MigrationCutoverResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGet**
> RevealListResponse getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGet(projectRef)

Get Api Key Reveals

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**RevealListResponse**](RevealListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getApiKeySlotsApiProjectsProjectRefApiKeySlotsGet**
> SlotListResponse getApiKeySlotsApiProjectsProjectRefApiKeySlotsGet(projectRef)

Get Api Key Slots

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getApiKeySlotsApiProjectsProjectRefApiKeySlotsGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->getApiKeySlotsApiProjectsProjectRefApiKeySlotsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**SlotListResponse**](SlotListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGet**
> MigrationStatusResponse getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGet(projectRef)

Get Opaque Api Key Migration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**MigrationStatusResponse**](MigrationStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePost**
> MigrationPrepareResponse prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePost(projectRef)

Prepare Opaque Api Key Migration

Prepare rejected opaque keys without changing the running gateway.

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePost(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**MigrationPrepareResponse**](MigrationPrepareResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDelete**
> SlotRevokeResponse revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDelete(projectRef, slotId, xStepUpToken)

Revoke Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final xStepUpToken = xStepUpToken_example; // String |

try {
    final result = api_instance.revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDelete(projectRef, slotId, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  | 
 **xStepUpToken** | **String**|  | [optional]

### Return type

[**SlotRevokeResponse**](SlotRevokeResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPost**
> IssuedKeyResponse rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPost(projectRef, slotId, rotateApiKeySlot, xStepUpToken)

Rotate Api Key Slot

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final rotateApiKeySlot = RotateApiKeySlot(); // RotateApiKeySlot | 
final xStepUpToken = xStepUpToken_example; // String | 

try {
    final result = api_instance.rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPost(projectRef, slotId, rotateApiKeySlot, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  | 
 **rotateApiKeySlot** | [**RotateApiKeySlot**](RotateApiKeySlot.md)|  | 
 **xStepUpToken** | **String**|  | [optional] 

### Return type

[**IssuedKeyResponse**](IssuedKeyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatch**
> SlotPolicyUpdateResponse updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatch(projectRef, slotId, updateApiKeySlotPolicy, xStepUpToken)

Update Api Key Slot Policy

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = OpaqueApiKeysApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String | 
final updateApiKeySlotPolicy = UpdateApiKeySlotPolicy(); // UpdateApiKeySlotPolicy | 
final xStepUpToken = xStepUpToken_example; // String |

try {
    final result = api_instance.updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatch(projectRef, slotId, updateApiKeySlotPolicy, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling OpaqueApiKeysApi->updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  | 
 **updateApiKeySlotPolicy** | [**UpdateApiKeySlotPolicy**](UpdateApiKeySlotPolicy.md)|  | 
 **xStepUpToken** | **String**|  | [optional]

### Return type

[**SlotPolicyUpdateResponse**](SlotPolicyUpdateResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

