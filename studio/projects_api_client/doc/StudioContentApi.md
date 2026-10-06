# projects_api_client.api.StudioContentApi

## Load the API package
```dart
import 'package:projects_api_client/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**contentCountApiProjectsRefContentCountGet**](StudioContentApi.md#contentcountapiprojectsrefcontentcountget) | **GET** /api/projects/{ref}/content/count | Content Count
[**contentDeleteApiProjectsRefContentDelete**](StudioContentApi.md#contentdeleteapiprojectsrefcontentdelete) | **DELETE** /api/projects/{ref}/content | Content Delete
[**contentItemApiProjectsRefContentItemIdGet**](StudioContentApi.md#contentitemapiprojectsrefcontentitemidget) | **GET** /api/projects/{ref}/content/item/{id} | Content Item
[**contentListApiProjectsRefContentGet**](StudioContentApi.md#contentlistapiprojectsrefcontentget) | **GET** /api/projects/{ref}/content | Content List
[**contentSaveApiProjectsRefContentPut**](StudioContentApi.md#contentsaveapiprojectsrefcontentput) | **PUT** /api/projects/{ref}/content | Content Save
[**folderCreateApiProjectsRefContentFoldersPost**](StudioContentApi.md#foldercreateapiprojectsrefcontentfolderspost) | **POST** /api/projects/{ref}/content/folders | Folder Create
[**folderItemApiProjectsRefContentFoldersIdGet**](StudioContentApi.md#folderitemapiprojectsrefcontentfoldersidget) | **GET** /api/projects/{ref}/content/folders/{id} | Folder Item
[**folderUpdateApiProjectsRefContentFoldersIdPatch**](StudioContentApi.md#folderupdateapiprojectsrefcontentfoldersidpatch) | **PATCH** /api/projects/{ref}/content/folders/{id} | Folder Update
[**foldersDeleteApiProjectsRefContentFoldersDelete**](StudioContentApi.md#foldersdeleteapiprojectsrefcontentfoldersdelete) | **DELETE** /api/projects/{ref}/content/folders | Folders Delete
[**foldersListApiProjectsRefContentFoldersGet**](StudioContentApi.md#folderslistapiprojectsrefcontentfoldersget) | **GET** /api/projects/{ref}/content/folders | Folders List


# **contentCountApiProjectsRefContentCountGet**
> Object contentCountApiProjectsRefContentCountGet(ref)

Content Count

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |

try {
    final result = api_instance.contentCountApiProjectsRefContentCountGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->contentCountApiProjectsRefContentCountGet: $e\n');
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

# **contentDeleteApiProjectsRefContentDelete**
> Object contentDeleteApiProjectsRefContentDelete(ref)

Content Delete

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |

try {
    final result = api_instance.contentDeleteApiProjectsRefContentDelete(ref);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->contentDeleteApiProjectsRefContentDelete: $e\n');
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

# **contentItemApiProjectsRefContentItemIdGet**
> Object contentItemApiProjectsRefContentItemIdGet(ref, id)

Content Item

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |
final id = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String |

try {
    final result = api_instance.contentItemApiProjectsRefContentItemIdGet(ref, id);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->contentItemApiProjectsRefContentItemIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **id** | **String**|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **contentListApiProjectsRefContentGet**
> Object contentListApiProjectsRefContentGet(ref)

Content List

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |

try {
    final result = api_instance.contentListApiProjectsRefContentGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->contentListApiProjectsRefContentGet: $e\n');
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

# **contentSaveApiProjectsRefContentPut**
> Object contentSaveApiProjectsRefContentPut(ref, snippetBody)

Content Save

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |
final snippetBody = SnippetBody(); // SnippetBody |

try {
    final result = api_instance.contentSaveApiProjectsRefContentPut(ref, snippetBody);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->contentSaveApiProjectsRefContentPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **snippetBody** | [**SnippetBody**](SnippetBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **folderCreateApiProjectsRefContentFoldersPost**
> Object folderCreateApiProjectsRefContentFoldersPost(ref, folderBody)

Folder Create

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |
final folderBody = FolderBody(); // FolderBody |

try {
    final result = api_instance.folderCreateApiProjectsRefContentFoldersPost(ref, folderBody);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->folderCreateApiProjectsRefContentFoldersPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **folderBody** | [**FolderBody**](FolderBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **folderItemApiProjectsRefContentFoldersIdGet**
> Object folderItemApiProjectsRefContentFoldersIdGet(ref, id)

Folder Item

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |
final id = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String |

try {
    final result = api_instance.folderItemApiProjectsRefContentFoldersIdGet(ref, id);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->folderItemApiProjectsRefContentFoldersIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **id** | **String**|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **folderUpdateApiProjectsRefContentFoldersIdPatch**
> Object folderUpdateApiProjectsRefContentFoldersIdPatch(ref, id, folderBody)

Folder Update

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |
final id = 38400000-8cf0-11bd-b23e-10b96e4ef00d; // String |
final folderBody = FolderBody(); // FolderBody |

try {
    final result = api_instance.folderUpdateApiProjectsRefContentFoldersIdPatch(ref, id, folderBody);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->folderUpdateApiProjectsRefContentFoldersIdPatch: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **ref** | **String**|  |
 **id** | **String**|  |
 **folderBody** | [**FolderBody**](FolderBody.md)|  |

### Return type

[**Object**](Object.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **foldersDeleteApiProjectsRefContentFoldersDelete**
> Object foldersDeleteApiProjectsRefContentFoldersDelete(ref)

Folders Delete

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |

try {
    final result = api_instance.foldersDeleteApiProjectsRefContentFoldersDelete(ref);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->foldersDeleteApiProjectsRefContentFoldersDelete: $e\n');
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

# **foldersListApiProjectsRefContentFoldersGet**
> Object foldersListApiProjectsRefContentFoldersGet(ref)

Folders List

### Example
```dart
import 'package:projects_api_client/api.dart';

final api_instance = StudioContentApi();
final ref = ref_example; // String |

try {
    final result = api_instance.foldersListApiProjectsRefContentFoldersGet(ref);
    print(result);
} catch (e) {
    print('Exception when calling StudioContentApi->foldersListApiProjectsRefContentFoldersGet: $e\n');
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

