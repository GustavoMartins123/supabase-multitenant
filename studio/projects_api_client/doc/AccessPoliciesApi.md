# projects_api_client.api.AccessPoliciesApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**countriesApiProjectsCountriesGet**](AccessPoliciesApi.md#countriesapiprojectscountriesget) | **GET** /api/projects/countries | Countries
[**projectPolicyApiProjectsProjectRefAccessPolicyGet**](AccessPoliciesApi.md#projectpolicyapiprojectsprojectrefaccesspolicyget) | **GET** /api/projects/{project_ref}/access-policy | Project Policy
[**slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGet**](AccessPoliciesApi.md#slotpolicyapiprojectsprojectrefapikeyslotsslotidaccesspolicyget) | **GET** /api/projects/{project_ref}/api-key-slots/{slot_id}/access-policy | Slot Policy
[**updateProjectPolicyApiProjectsProjectRefAccessPolicyPut**](AccessPoliciesApi.md#updateprojectpolicyapiprojectsprojectrefaccesspolicyput) | **PUT** /api/projects/{project_ref}/access-policy | Update Project Policy
[**updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPut**](AccessPoliciesApi.md#updateslotpolicyapiprojectsprojectrefapikeyslotsslotidaccesspolicyput) | **PUT** /api/projects/{project_ref}/api-key-slots/{slot_id}/access-policy | Update Slot Policy
[**usageApiProjectsProjectRefAccessUsageGet**](AccessPoliciesApi.md#usageapiprojectsprojectrefaccessusageget) | **GET** /api/projects/{project_ref}/access-usage | Usage


# **countriesApiProjectsCountriesGet**
> CountryCatalog countriesApiProjectsCountriesGet()

Countries

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AccessPoliciesApi();

try {
    final result = api_instance.countriesApiProjectsCountriesGet();
    print(result);
} catch (e) {
    print('Exception when calling AccessPoliciesApi->countriesApiProjectsCountriesGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**CountryCatalog**](CountryCatalog.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **projectPolicyApiProjectsProjectRefAccessPolicyGet**
> PolicyResponse projectPolicyApiProjectsProjectRefAccessPolicyGet(projectRef)

Project Policy

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AccessPoliciesApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.projectPolicyApiProjectsProjectRefAccessPolicyGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling AccessPoliciesApi->projectPolicyApiProjectsProjectRefAccessPolicyGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**PolicyResponse**](PolicyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGet**
> PolicyResponse slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGet(projectRef, slotId)

Slot Policy

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AccessPoliciesApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String |

try {
    final result = api_instance.slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGet(projectRef, slotId);
    print(result);
} catch (e) {
    print('Exception when calling AccessPoliciesApi->slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  |

### Return type

[**PolicyResponse**](PolicyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProjectPolicyApiProjectsProjectRefAccessPolicyPut**
> PolicyResponse updateProjectPolicyApiProjectsProjectRefAccessPolicyPut(projectRef, policyUpdate, xStepUpToken)

Update Project Policy

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AccessPoliciesApi();
final projectRef = projectRef_example; // String |
final policyUpdate = PolicyUpdate(); // PolicyUpdate |
final xStepUpToken = xStepUpToken_example; // String |

try {
    final result = api_instance.updateProjectPolicyApiProjectsProjectRefAccessPolicyPut(projectRef, policyUpdate, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling AccessPoliciesApi->updateProjectPolicyApiProjectsProjectRefAccessPolicyPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **policyUpdate** | [**PolicyUpdate**](PolicyUpdate.md)|  |
 **xStepUpToken** | **String**|  | [optional]

### Return type

[**PolicyResponse**](PolicyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPut**
> PolicyResponse updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPut(projectRef, slotId, policyUpdate, xStepUpToken)

Update Slot Policy

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AccessPoliciesApi();
final projectRef = projectRef_example; // String |
final slotId = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String |
final policyUpdate = PolicyUpdate(); // PolicyUpdate |
final xStepUpToken = xStepUpToken_example; // String |

try {
    final result = api_instance.updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPut(projectRef, slotId, policyUpdate, xStepUpToken);
    print(result);
} catch (e) {
    print('Exception when calling AccessPoliciesApi->updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |
 **slotId** | **String**|  |
 **policyUpdate** | [**PolicyUpdate**](PolicyUpdate.md)|  |
 **xStepUpToken** | **String**|  | [optional]

### Return type

[**PolicyResponse**](PolicyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **usageApiProjectsProjectRefAccessUsageGet**
> AccessUsageResponse usageApiProjectsProjectRefAccessUsageGet(projectRef)

Usage

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AccessPoliciesApi();
final projectRef = projectRef_example; // String |

try {
    final result = api_instance.usageApiProjectsProjectRefAccessUsageGet(projectRef);
    print(result);
} catch (e) {
    print('Exception when calling AccessPoliciesApi->usageApiProjectsProjectRefAccessUsageGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **projectRef** | **String**|  |

### Return type

[**AccessUsageResponse**](AccessUsageResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

