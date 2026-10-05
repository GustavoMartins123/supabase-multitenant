# projects_api_client.api.AssistantApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**assistantContextApiProjectsRefAssistantContextGet**](AssistantApi.md#assistantcontextapiprojectsrefassistantcontextget) | **GET** /api/projects/{ref}/assistant/context | Assistant Context
[**assistantExecuteApiProjectsRefAssistantExecutePost**](AssistantApi.md#assistantexecuteapiprojectsrefassistantexecutepost) | **POST** /api/projects/{ref}/assistant/execute | Assistant Execute
[**assistantFunctionsApiProjectsRefAssistantFunctionsGet**](AssistantApi.md#assistantfunctionsapiprojectsrefassistantfunctionsget) | **GET** /api/projects/{ref}/assistant/functions | Assistant Functions
[**assistantPrivilegesApiProjectsRefAssistantPrivilegesPost**](AssistantApi.md#assistantprivilegesapiprojectsrefassistantprivilegespost) | **POST** /api/projects/{ref}/assistant/privileges | Assistant Privileges
[**assistantRowsApiProjectsRefAssistantRowsPost**](AssistantApi.md#assistantrowsapiprojectsrefassistantrowspost) | **POST** /api/projects/{ref}/assistant/rows | Assistant Rows
[**assistantSchemaApiProjectsRefAssistantSchemaGet**](AssistantApi.md#assistantschemaapiprojectsrefassistantschemaget) | **GET** /api/projects/{ref}/assistant/schema | Assistant Schema
[**assistantSecurityApiProjectsRefAssistantSecurityPost**](AssistantApi.md#assistantsecurityapiprojectsrefassistantsecuritypost) | **POST** /api/projects/{ref}/assistant/security | Assistant Security
[**assistantSqlApiProjectsRefAssistantSqlPost**](AssistantApi.md#assistantsqlapiprojectsrefassistantsqlpost) | **POST** /api/projects/{ref}/assistant/sql | Assistant Sql


# **assistantContextApiProjectsRefAssistantContextGet**
> Object assistantContextApiProjectsRefAssistantContextGet(ref)

Assistant Context

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |

try {
    final result = api_instance.assistantContextApiProjectsRefAssistantContextGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantContextApiProjectsRefAssistantContextGet: $e\n');
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

# **assistantExecuteApiProjectsRefAssistantExecutePost**
> Object assistantExecuteApiProjectsRefAssistantExecutePost(ref, requestBody)

Assistant Execute

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |
final requestBody = Map<String, Object>(); // Map<String, Object> |

try {
    final result = api_instance.assistantExecuteApiProjectsRefAssistantExecutePost(ref, requestBody);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantExecuteApiProjectsRefAssistantExecutePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **requestBody** | [**Map<String, Object>**](Object.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **assistantFunctionsApiProjectsRefAssistantFunctionsGet**
> Object assistantFunctionsApiProjectsRefAssistantFunctionsGet(ref)

Assistant Functions

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |

try {
    final result = api_instance.assistantFunctionsApiProjectsRefAssistantFunctionsGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantFunctionsApiProjectsRefAssistantFunctionsGet: $e\n');
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

# **assistantPrivilegesApiProjectsRefAssistantPrivilegesPost**
> Object assistantPrivilegesApiProjectsRefAssistantPrivilegesPost(ref, privilegeChangeBody)

Assistant Privileges

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |
final privilegeChangeBody = PrivilegeChangeBody(); // PrivilegeChangeBody |

try {
    final result = api_instance.assistantPrivilegesApiProjectsRefAssistantPrivilegesPost(ref, privilegeChangeBody);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantPrivilegesApiProjectsRefAssistantPrivilegesPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **privilegeChangeBody** | [**PrivilegeChangeBody**](PrivilegeChangeBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **assistantRowsApiProjectsRefAssistantRowsPost**
> Object assistantRowsApiProjectsRefAssistantRowsPost(ref, readRowsBody)

Assistant Rows

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |
final readRowsBody = ReadRowsBody(); // ReadRowsBody |

try {
    final result = api_instance.assistantRowsApiProjectsRefAssistantRowsPost(ref, readRowsBody);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantRowsApiProjectsRefAssistantRowsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **readRowsBody** | [**ReadRowsBody**](ReadRowsBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **assistantSchemaApiProjectsRefAssistantSchemaGet**
> Object assistantSchemaApiProjectsRefAssistantSchemaGet(ref)

Assistant Schema

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |

try {
    final result = api_instance.assistantSchemaApiProjectsRefAssistantSchemaGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantSchemaApiProjectsRefAssistantSchemaGet: $e\n');
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

# **assistantSecurityApiProjectsRefAssistantSecurityPost**
> Object assistantSecurityApiProjectsRefAssistantSecurityPost(ref, securityBody)

Assistant Security

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |
final securityBody = SecurityBody(); // SecurityBody |

try {
    final result = api_instance.assistantSecurityApiProjectsRefAssistantSecurityPost(ref, securityBody);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantSecurityApiProjectsRefAssistantSecurityPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **securityBody** | [**SecurityBody**](SecurityBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **assistantSqlApiProjectsRefAssistantSqlPost**
> Object assistantSqlApiProjectsRefAssistantSqlPost(ref, executeSqlBody)

Assistant Sql

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = AssistantApi();
final ref = ref_example; // String |
final executeSqlBody = ExecuteSqlBody(); // ExecuteSqlBody |

try {
    final result = api_instance.assistantSqlApiProjectsRefAssistantSqlPost(ref, executeSqlBody);
    print(result);
} catch (e) {
    print('Exception when calling AssistantApi->assistantSqlApiProjectsRefAssistantSqlPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **executeSqlBody** | [**ExecuteSqlBody**](ExecuteSqlBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

