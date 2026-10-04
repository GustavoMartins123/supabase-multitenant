# projects_api_client.api.ClientConfigurationApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getClientConfigurationConfigApplicationRefGet**](ClientConfigurationApi.md#getclientconfigurationconfigapplicationrefget) | **GET** /config/{application_ref} | Get Client Configuration


# **getClientConfigurationConfigApplicationRefGet**
> ClientConfigurationResponse getClientConfigurationConfigApplicationRefGet(applicationRef)

Get Client Configuration

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = ClientConfigurationApi();
final applicationRef = applicationRef_example; // String |

try {
    final result = api_instance.getClientConfigurationConfigApplicationRefGet(applicationRef);
    print(result);
} catch (e) {
    print('Exception when calling ClientConfigurationApi->getClientConfigurationConfigApplicationRefGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **applicationRef** | **String**|  |

### Return type

[**ClientConfigurationResponse**](ClientConfigurationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

